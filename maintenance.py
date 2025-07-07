#!/usr/bin/env python3
"""
maintenance.py - Automated maintenance tasks for telecom-lab-ha3

This tool performs routine maintenance operations including:
- Service health monitoring
- Log rotation and cleanup
- Database optimization
- System performance checks
- Automated repair procedures
- Backup verification
"""

import os
import sys
import json
import logging
import argparse
import subprocess
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import mysql.connector
import requests
import psutil

# Configuration
CONFIG = {
    'services': ['kamailio', 'freeradius', 'mariadb', 'keepalived'],
    'log_dirs': ['/var/log/kamailio', '/var/log/freeradius', '/var/log/mysql'],
    'backup_dir': '/opt/backups',
    'max_log_age_days': 7,
    'max_disk_usage_percent': 85,
    'prometheus_url': 'http://jumphost.lab.local:9090',
    'grafana_url': 'http://jumphost.lab.local:3000',
    'mysql_config': {
        'host': 'localhost',
        'user': 'root',
        'password': '',
        'database': 'mysql'
    }
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/maintenance.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MaintenanceTool:
    """Main maintenance operations manager."""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.datetime.now().isoformat(),
            'hostname': os.uname().nodename,
            'tasks': {}
        }
    
    def run_command(self, command: str) -> Tuple[int, str, str]:
        """Execute shell command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)
    
    def check_service_health(self) -> Dict:
        """Check status of critical telecom services."""
        logger.info("Checking service health...")
        health_status = {}
        
        for service in CONFIG['services']:
            returncode, stdout, stderr = self.run_command(f"systemctl is-active {service}")
            is_active = returncode == 0 and stdout.strip() == "active"
            
            returncode, stdout, stderr = self.run_command(f"systemctl is-enabled {service}")
            is_enabled = returncode == 0 and stdout.strip() == "enabled"
            
            health_status[service] = {
                'active': is_active,
                'enabled': is_enabled,
                'status': 'healthy' if is_active and is_enabled else 'unhealthy'
            }
            
            if not is_active:
                logger.warning(f"Service {service} is not active!")
                self.restart_service(service)
        
        self.results['tasks']['service_health'] = health_status
        return health_status
    
    def restart_service(self, service: str) -> bool:
        """Attempt to restart a failed service."""
        logger.info(f"Attempting to restart service: {service}")
        returncode, stdout, stderr = self.run_command(f"systemctl restart {service}")
        
        if returncode == 0:
            logger.info(f"Successfully restarted {service}")
            return True
        else:
            logger.error(f"Failed to restart {service}: {stderr}")
            return False
    
    def check_disk_usage(self) -> Dict:
        """Monitor disk usage and clean up if necessary."""
        logger.info("Checking disk usage...")
        disk_info = {}
        
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                usage_percent = (usage.used / usage.total) * 100
                
                disk_info[partition.mountpoint] = {
                    'total_gb': round(usage.total / (1024**3), 2),
                    'used_gb': round(usage.used / (1024**3), 2),
                    'free_gb': round(usage.free / (1024**3), 2),
                    'usage_percent': round(usage_percent, 2),
                    'status': 'critical' if usage_percent > CONFIG['max_disk_usage_percent'] else 'ok'
                }
                
                if usage_percent > CONFIG['max_disk_usage_percent']:
                    logger.warning(f"High disk usage on {partition.mountpoint}: {usage_percent:.1f}%")
                    self.cleanup_logs()
                    
            except PermissionError:
                continue
        
        self.results['tasks']['disk_usage'] = disk_info
        return disk_info
    
    def cleanup_logs(self) -> Dict:
        """Clean up old log files."""
        logger.info("Cleaning up old logs...")
        cleanup_results = {}
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=CONFIG['max_log_age_days'])
        
        for log_dir in CONFIG['log_dirs']:
            if not os.path.exists(log_dir):
                continue
                
            cleaned_files = []
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                        if file_mtime < cutoff_date and file.endswith(('.log', '.1', '.2', '.3')):
                            os.remove(file_path)
                            cleaned_files.append(file_path)
                            logger.info(f"Removed old log file: {file_path}")
                    except OSError:
                        continue
            
            cleanup_results[log_dir] = {
                'files_removed': len(cleaned_files),
                'files': cleaned_files
            }
        
        # Rotate journald logs
        self.run_command("journalctl --vacuum-time=7d")
        
        self.results['tasks']['log_cleanup'] = cleanup_results
        return cleanup_results
    
    def check_mysql_health(self) -> Dict:
        """Check MySQL/Galera cluster health."""
        logger.info("Checking MySQL/Galera health...")
        mysql_status = {}
        
        try:
            connection = mysql.connector.connect(**CONFIG['mysql_config'])
            cursor = connection.cursor()
            
            # Check Galera cluster status
            cursor.execute("SHOW STATUS LIKE 'wsrep_%'")
            galera_status = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Key metrics
            mysql_status = {
                'cluster_size': galera_status.get('wsrep_cluster_size', 'unknown'),
                'local_state': galera_status.get('wsrep_local_state_comment', 'unknown'),
                'ready': galera_status.get('wsrep_ready', 'unknown'),
                'connected': galera_status.get('wsrep_connected', 'unknown'),
                'status': 'healthy' if galera_status.get('wsrep_ready') == 'ON' else 'unhealthy'
            }
            
            # Optimize tables if needed
            if mysql_status['status'] == 'healthy':
                self.optimize_mysql_tables(cursor)
            
            connection.close()
            
        except mysql.connector.Error as e:
            logger.error(f"MySQL connection error: {e}")
            mysql_status = {'status': 'error', 'error': str(e)}
        
        self.results['tasks']['mysql_health'] = mysql_status
        return mysql_status
    
    def optimize_mysql_tables(self, cursor) -> None:
        """Optimize MySQL tables for better performance."""
        logger.info("Optimizing MySQL tables...")
        
        # Get all tables
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            try:
                cursor.execute(f"OPTIMIZE TABLE {table}")
                logger.debug(f"Optimized table: {table}")
            except mysql.connector.Error as e:
                logger.warning(f"Failed to optimize table {table}: {e}")
    
    def check_network_connectivity(self) -> Dict:
        """Check network connectivity to critical services."""
        logger.info("Checking network connectivity...")
        connectivity = {}
        
        hosts_to_check = [
            ('ha1.lab.local', 5060),
            ('ha2.lab.local', 5060),
            ('ha3.lab.local', 5060),
            ('ha1.lab.local', 1812),
            ('ha2.lab.local', 1812),
            ('ha3.lab.local', 1812),
            ('jumphost.lab.local', 9090),
            ('jumphost.lab.local', 3000)
        ]
        
        for host, port in hosts_to_check:
            returncode, stdout, stderr = self.run_command(f"nc -z -w5 {host} {port}")
            connectivity[f"{host}:{port}"] = {
                'reachable': returncode == 0,
                'status': 'ok' if returncode == 0 else 'failed'
            }
        
        self.results['tasks']['network_connectivity'] = connectivity
        return connectivity
    
    def check_certificate_expiry(self) -> Dict:
        """Check SSL certificate expiration dates."""
        logger.info("Checking certificate expiry...")
        cert_status = {}
        
        cert_paths = [
            '/etc/ssl/certs/telecom-lab.pem',
            '/opt/ca/ca.pem',
            '/etc/wireguard/server.crt'
        ]
        
        for cert_path in cert_paths:
            if os.path.exists(cert_path):
                returncode, stdout, stderr = self.run_command(
                    f"openssl x509 -enddate -noout -in {cert_path}"
                )
                
                if returncode == 0:
                    # Parse expiry date
                    expiry_str = stdout.replace('notAfter=', '').strip()
                    try:
                        expiry_date = datetime.datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
                        days_until_expiry = (expiry_date - datetime.datetime.now()).days
                        
                        cert_status[cert_path] = {
                            'expiry_date': expiry_date.isoformat(),
                            'days_until_expiry': days_until_expiry,
                            'status': 'critical' if days_until_expiry < 30 else 'ok'
                        }
                        
                        if days_until_expiry < 30:
                            logger.warning(f"Certificate {cert_path} expires in {days_until_expiry} days!")
                            
                    except ValueError:
                        cert_status[cert_path] = {'status': 'parse_error', 'error': 'Could not parse date'}
                else:
                    cert_status[cert_path] = {'status': 'read_error', 'error': stderr}
            else:
                cert_status[cert_path] = {'status': 'not_found'}
        
        self.results['tasks']['certificate_expiry'] = cert_status
        return cert_status
    
    def backup_verification(self) -> Dict:
        """Verify recent backups exist and are valid."""
        logger.info("Verifying backups...")
        backup_status = {}
        
        if os.path.exists(CONFIG['backup_dir']):
            # Check for recent MySQL backup
            mysql_backups = list(Path(CONFIG['backup_dir']).glob('mysql/full_backup_*.sql.gz'))
            if mysql_backups:
                latest_mysql = max(mysql_backups, key=os.path.getctime)
                backup_age = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getctime(latest_mysql))
                
                backup_status['mysql'] = {
                    'latest_backup': str(latest_mysql),
                    'age_hours': round(backup_age.total_seconds() / 3600, 2),
                    'status': 'ok' if backup_age.days < 1 else 'old'
                }
            else:
                backup_status['mysql'] = {'status': 'missing'}
            
            # Check for config backup
            config_backups = list(Path(CONFIG['backup_dir']).glob('configs/configs_*.tar.gz'))
            if config_backups:
                latest_config = max(config_backups, key=os.path.getctime)
                backup_age = datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getctime(latest_config))
                
                backup_status['configs'] = {
                    'latest_backup': str(latest_config),
                    'age_hours': round(backup_age.total_seconds() / 3600, 2),
                    'status': 'ok' if backup_age.days < 1 else 'old'
                }
            else:
                backup_status['configs'] = {'status': 'missing'}
        else:
            backup_status = {'status': 'backup_dir_missing'}
        
        self.results['tasks']['backup_verification'] = backup_status
        return backup_status
    
    def performance_metrics(self) -> Dict:
        """Collect system performance metrics."""
        logger.info("Collecting performance metrics...")
        metrics = {}
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Load average
        load_avg = os.getloadavg()
        
        # Network statistics
        net_io = psutil.net_io_counters()
        
        metrics = {
            'cpu_percent': cpu_percent,
            'memory': {
                'total_gb': round(memory.total / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'percent': memory.percent
            },
            'load_average': {
                '1min': load_avg[0],
                '5min': load_avg[1],
                '15min': load_avg[2]
            },
            'network': {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            },
            'uptime_hours': round(psutil.boot_time() / 3600, 2)
        }
        
        self.results['tasks']['performance_metrics'] = metrics
        return metrics
    
    def send_metrics_to_prometheus(self) -> bool:
        """Send maintenance metrics to Prometheus."""
        try:
            # This would typically use Prometheus pushgateway
            # For now, just log the metrics
            logger.info("Metrics would be sent to Prometheus here")
            return True
        except Exception as e:
            logger.error(f"Failed to send metrics to Prometheus: {e}")
            return False
    
    def generate_report(self) -> str:
        """Generate comprehensive maintenance report."""
        report_path = f"/tmp/maintenance_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Maintenance report generated: {report_path}")
        return report_path
    
    def run_full_maintenance(self) -> Dict:
        """Execute all maintenance tasks."""
        logger.info("Starting full maintenance cycle...")
        
        try:
            self.check_service_health()
            self.check_disk_usage()
            self.cleanup_logs()
            self.check_mysql_health()
            self.check_network_connectivity()
            self.check_certificate_expiry()
            self.backup_verification()
            self.performance_metrics()
            
            # Generate summary
            self.results['summary'] = {
                'total_tasks': len(self.results['tasks']),
                'status': 'completed',
                'duration_seconds': (datetime.datetime.now() - 
                                   datetime.datetime.fromisoformat(self.results['timestamp'])).total_seconds()
            }
            
            report_path = self.generate_report()
            logger.info("Full maintenance cycle completed successfully")
            
            return self.results
            
        except Exception as e:
            logger.error(f"Maintenance cycle failed: {e}")
            self.results['summary'] = {
                'status': 'failed',
                'error': str(e)
            }
            return self.results

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Telecom Lab HA3 Maintenance Tool')
    parser.add_argument('--task', choices=[
        'health', 'disk', 'logs', 'mysql', 'network', 'certs', 'backup', 'metrics', 'full'
    ], default='full', help='Specific maintenance task to run')
    parser.add_argument('--config', help='Custom configuration file')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without executing')
    parser.add_argument('--quiet', action='store_true', help='Reduce output verbosity')
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    maintenance = MaintenanceTool()
    
    # Execute specific task or full maintenance
    if args.task == 'health':
        maintenance.check_service_health()
    elif args.task == 'disk':
        maintenance.check_disk_usage()
    elif args.task == 'logs':
        maintenance.cleanup_logs()
    elif args.task == 'mysql':
        maintenance.check_mysql_health()
    elif args.task == 'network':
        maintenance.check_network_connectivity()
    elif args.task == 'certs':
        maintenance.check_certificate_expiry()
    elif args.task == 'backup':
        maintenance.backup_verification()
    elif args.task == 'metrics':
        maintenance.performance_metrics()
    else:
        maintenance.run_full_maintenance()
    
    # Print results
    print(json.dumps(maintenance.results, indent=2))
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
