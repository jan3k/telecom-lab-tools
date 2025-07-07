#!/usr/bin/env python3
"""
backup_restore.py - Comprehensive backup and restore for telecom-lab-ha3
"""

import os
import sys
import json
import shutil
import subprocess
import tarfile
import gzip
import datetime
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/backup-restore.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelecomBackup:
    def __init__(self, backup_dir: str = "/opt/backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration paths
        self.config_paths = {
            'kamailio': ['/etc/kamailio'],
            'freeradius': ['/etc/freeradius'],
            'mariadb': ['/etc/mysql'],
            'keepalived': ['/etc/keepalived'],
            'puppet': ['/etc/puppetlabs'],
            'monitoring': ['/opt/monitoring'],
            'ssl_certs': ['/etc/ssl', '/opt/ca'],
            'wireguard': ['/etc/wireguard'],
            'haproxy': ['/etc/haproxy']
        }
        
        # Database configuration
        self.db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',  # Will be read from file or env
            'databases': ['kamailio', 'radius', 'mysql']
        }
        
    def create_timestamp(self) -> str:
        """Create timestamp for backup naming"""
        return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def backup_configurations(self, timestamp: str) -> Dict[str, str]:
        """Backup all configuration files"""
        logger.info("Starting configuration backup...")
        
        config_backup_dir = self.backup_dir / f"config_{timestamp}"
        config_backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_results = {}
        
        for service, paths in self.config_paths.items():
            logger.info(f"Backing up {service} configuration...")
            
            service_backup_dir = config_backup_dir / service
            service_backup_dir.mkdir(parents=True, exist_ok=True)
            
            for path in paths:
                source_path = Path(path)
                if source_path.exists():
                    if source_path.is_dir():
                        dest_path = service_backup_dir / source_path.name
                        try:
                            shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                            backup_results[f"{service}_{source_path.name}"] = "success"
                        except Exception as e:
                            logger.error(f"Failed to backup {path}: {e}")
                            backup_results[f"{service}_{source_path.name}"] = f"error: {e}"
                    else:
                        try:
                            shutil.copy2(source_path, service_backup_dir)
                            backup_results[f"{service}_{source_path.name}"] = "success"
                        except Exception as e:
                            logger.error(f"Failed to backup {path}: {e}")
                            backup_results[f"{service}_{source_path.name}"] = f"error: {e}"
                else:
                    logger.warning(f"Path does not exist: {path}")
                    backup_results[f"{service}_{source_path.name}"] = "path_not_found"
        
        # Create compressed archive
        archive_path = self.backup_dir / f"config_backup_{timestamp}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(config_backup_dir, arcname=f"config_{timestamp}")
        
        # Remove uncompressed directory
        shutil.rmtree(config_backup_dir)
        
        logger.info(f"Configuration backup completed: {archive_path}")
        return backup_results
    
    def backup_databases(self, timestamp: str) -> Dict[str, str]:
        """Backup MySQL/MariaDB databases"""
        logger.info("Starting database backup...")
        
        db_backup_dir = self.backup_dir / f"database_{timestamp}"
        db_backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_results = {}
        
        # Check if MySQL is running
        try:
            result = subprocess.run(['systemctl', 'is-active', 'mariadb'], 
                                 capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("MariaDB service is not running")
                return {"database_service": "not_running"}
        except Exception as e:
            logger.error(f"Failed to check MariaDB status: {e}")
            return {"database_check": f"error: {e}"}
        
        # Backup individual databases
        for database in self.db_config['databases']:
            logger.info(f"Backing up database: {database}")
            
            backup_file = db_backup_dir / f"{database}_{timestamp}.sql"
            
            try:
                cmd = [
                    'mysqldump',
                    '-u', self.db_config['user'],
                    '--single-transaction',
                    '--routines',
                    '--triggers',
                    database
                ]
                
                with open(backup_file, 'w') as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                
                if result.returncode == 0:
                    # Compress the SQL file
                    with open(backup_file, 'rb') as f_in:
                        with gzip.open(f"{backup_file}.gz", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    
                    # Remove uncompressed file
                    backup_file.unlink()
                    
                    backup_results[database] = "success"
                    logger.info(f"Database {database} backed up successfully")
                else:
                    logger.error(f"Failed to backup database {database}: {result.stderr}")
                    backup_results[database] = f"error: {result.stderr}"
            
            except Exception as e:
                logger.error(f"Exception during {database} backup: {e}")
                backup_results[database] = f"exception: {e}"
        
        # Create Galera cluster info backup
        try:
            cluster_info_file = db_backup_dir / f"galera_cluster_info_{timestamp}.txt"
            
            # Get cluster status
            cmd = ['mysql', '-u', 'root', '-e', 
                  "SHOW STATUS LIKE 'wsrep_%'; SHOW VARIABLES LIKE 'wsrep_%';"]
            
            with open(cluster_info_file, 'w') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode == 0:
                backup_results['galera_cluster_info'] = "success"
            else:
                backup_results['galera_cluster_info'] = f"error: {result.stderr}"
                
        except Exception as e:
            backup_results['galera_cluster_info'] = f"exception: {e}"
        
        # Create final database archive
        db_archive_path = self.backup_dir / f"database_backup_{timestamp}.tar.gz"
        with tarfile.open(db_archive_path, "w:gz") as tar:
            tar.add(db_backup_dir, arcname=f"database_{timestamp}")
        
        # Remove uncompressed directory
        shutil.rmtree(db_backup_dir)
        
        logger.info(f"Database backup completed: {db_archive_path}")
        return backup_results
    
    def backup_monitoring_data(self, timestamp: str) -> Dict[str, str]:
        """Backup monitoring data and configurations"""
        logger.info("Starting monitoring data backup...")
        
        monitoring_backup_dir = self.backup_dir / f"monitoring_{timestamp}"
        monitoring_backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_results = {}
        
        # Backup Prometheus data
        prometheus_data_dir = Path("/var/lib/docker/volumes")
        if prometheus_data_dir.exists():
            try:
                # Find Prometheus volume
                for volume_dir in prometheus_data_dir.glob("*prometheus*"):
                    dest_dir = monitoring_backup_dir / volume_dir.name
                    shutil.copytree(volume_dir, dest_dir, dirs_exist_ok=True)
                    backup_results[f"prometheus_volume_{volume_dir.name}"] = "success"
            except Exception as e:
                backup_results['prometheus_data'] = f"error: {e}"
        
        # Backup Grafana data
        grafana_data_dir = Path("/var/lib/docker/volumes")
        if grafana_data_dir.exists():
            try:
                for volume_dir in grafana_data_dir.glob("*grafana*"):
                    dest_dir = monitoring_backup_dir / volume_dir.name
                    shutil.copytree(volume_dir, dest_dir, dirs_exist_ok=True)
                    backup_results[f"grafana_volume_{volume_dir.name}"] = "success"
            except Exception as e:
                backup_results['grafana_data'] = f"error: {e}"
        
        # Export Grafana dashboards
        try:
            grafana_export_dir = monitoring_backup_dir / "grafana_export"
            grafana_export_dir.mkdir(parents=True, exist_ok=True)
            
            # This would require Grafana API calls
            # For now, just copy existing dashboard files
            dashboard_source = Path("/opt/monitoring/grafana/dashboards")
            if dashboard_source.exists():
                shutil.copytree(dashboard_source, grafana_export_dir / "dashboards", dirs_exist_ok=True)
                backup_results['grafana_dashboards'] = "success"
        except Exception as e:
            backup_results['grafana_dashboards'] = f"error: {e}"
        
        # Create monitoring archive
        monitoring_archive_path = self.backup_dir / f"monitoring_backup_{timestamp}.tar.gz"
        with tarfile.open(monitoring_archive_path, "w:gz") as tar:
            tar.add(monitoring_backup_dir, arcname=f"monitoring_{timestamp}")
        
        shutil.rmtree(monitoring_backup_dir)
        
        logger.info(f"Monitoring backup completed: {monitoring_archive_path}")
        return backup_results
    
    def create_full_backup(self) -> Dict:
        """Create a complete system backup"""
        timestamp = self.create_timestamp()
        logger.info(f"Starting full backup with timestamp: {timestamp}")
        
        backup_info = {
            'timestamp': timestamp,
            'hostname': os.uname().nodename,
            'backup_type': 'full',
            'results': {}
        }
        
        # Configuration backup
        try:
            config_results = self.backup_configurations(timestamp)
            backup_info['results']['configurations'] = config_results
        except Exception as e:
            logger.error(f"Configuration backup failed: {e}")
            backup_info['results']['configurations'] = {'error': str(e)}
        
        # Database backup
        try:
            db_results = self.backup_databases(timestamp)
            backup_info['results']['databases'] = db_results
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            backup_info['results']['databases'] = {'error': str(e)}
        
        # Monitoring backup
        try:
            monitoring_results = self.backup_monitoring_data(timestamp)
            backup_info['results']['monitoring'] = monitoring_results
        except Exception as e:
            logger.error(f"Monitoring backup failed: {e}")
            backup_info['results']['monitoring'] = {'error': str(e)}
        
        # Save backup metadata
        metadata_file = self.backup_dir / f"backup_metadata_{timestamp}.json"
        with open(metadata_file, 'w') as f:
            json.dump(backup_info, f, indent=2)
        
        logger.info(f"Full backup completed. Metadata saved to: {metadata_file}")
        return backup_info
    
    def list_backups(self) -> List[Dict]:
        """List available backups"""
        backups = []
        
        for metadata_file in self.backup_dir.glob("backup_metadata_*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    backup_info = json.load(f)
                    
                # Add file size information
                timestamp = backup_info['timestamp']
                total_size = 0
                
                for backup_file in self.backup_dir.glob(f"*_{timestamp}.*"):
                    total_size += backup_file.stat().st_size
                
                backup_info['total_size_mb'] = round(total_size / (1024 * 1024), 2)
                backups.append(backup_info)
                
            except Exception as e:
                logger.error(f"Failed to read backup metadata {metadata_file}: {e}")
        
        return sorted(backups, key=lambda x: x['timestamp'], reverse=True)
    
    def restore_configuration(self, timestamp: str, service: Optional[str] = None) -> bool:
        """Restore configuration from backup"""
        logger.info(f"Restoring configuration from backup: {timestamp}")
        
        config_archive = self.backup_dir / f"config_backup_{timestamp}.tar.gz"
        
        if not config_archive.exists():
            logger.error(f"Configuration backup not found: {config_archive}")
            return False
        
        try:
            # Extract to temporary directory
            temp_dir = self.backup_dir / f"temp_restore_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            with tarfile.open(config_archive, "r:gz") as tar:
                tar.extractall(temp_dir)
            
            config_dir = temp_dir / f"config_{timestamp}"
            
            if service:
                # Restore specific service
                service_dir = config_dir / service
                if service_dir.exists():
                    for path in self.config_paths.get(service, []):
                        source = service_dir / Path(path).name
                        if source.exists():
                            logger.info(f"Restoring {service} config to {path}")
                            if Path(path).is_dir():
                                shutil.rmtree(path)
                                shutil.copytree(source, path)
                            else:
                                shutil.copy2(source, path)
                else:
                    logger.error(f"Service {service} not found in backup")
                    return False
            else:
                # Restore all configurations
                for service_name in self.config_paths.keys():
                    service_dir = config_dir / service_name
                    if service_dir.exists():
                        for path in self.config_paths[service_name]:
                            source = service_dir / Path(path).name
                            if source.exists():
                                logger.info(f"Restoring {service_name} config to {path}")
                                if Path(path).exists():
                                    if Path(path).is_dir():
                                        shutil.rmtree(path)
                                    else:
                                        Path(path).unlink()
                                
                                if source.is_dir():
                                    shutil.copytree(source, path)
                                else:
                                    shutil.copy2(source, path)
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            logger.info("Configuration restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Configuration restore failed: {e}")
            return False
    
    def restore_database(self, timestamp: str, database: Optional[str] = None) -> bool:
        """Restore database from backup"""
        logger.info(f"Restoring database from backup: {timestamp}")
        
        db_archive = self.backup_dir / f"database_backup_{timestamp}.tar.gz"
        
        if not db_archive.exists():
            logger.error(f"Database backup not found: {db_archive}")
            return False
        
        try:
            # Extract to temporary directory
            temp_dir = self.backup_dir / f"temp_db_restore_{timestamp}"
            temp_dir.mkdir(exist_ok=True)
            
            with tarfile.open(db_archive, "r:gz") as tar:
                tar.extractall(temp_dir)
            
            db_dir = temp_dir / f"database_{timestamp}"
            
            databases_to_restore = [database] if database else self.db_config['databases']
            
            for db_name in databases_to_restore:
                sql_file = db_dir / f"{db_name}_{timestamp}.sql.gz"
                
                if sql_file.exists():
                    logger.info(f"Restoring database: {db_name}")
                    
                    # Decompress and restore
                    with gzip.open(sql_file, 'rt') as f:
                        cmd = ['mysql', '-u', self.db_config['user'], db_name]
                        result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
                        
                        if result.returncode == 0:
                            logger.info(f"Database {db_name} restored successfully")
                        else:
                            logger.error(f"Failed to restore database {db_name}: {result.stderr}")
                            return False
                else:
                    logger.error(f"Backup file not found for database: {db_name}")
                    return False
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            logger.info("Database restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database restore failed: {e}")
            return False
    
    def cleanup_old_backups(self, keep_days: int = 30) -> int:
        """Remove backups older than specified days"""
        logger.info(f"Cleaning up backups older than {keep_days} days...")
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=keep_days)
        removed_count = 0
        
        for backup_file in self.backup_dir.glob("*backup_*.tar.gz"):
            file_time = datetime.datetime.fromtimestamp(backup_file.stat().st_mtime)
            
            if file_time < cutoff_date:
                logger.info(f"Removing old backup: {backup_file}")
                backup_file.unlink()
                removed_count += 1
                
                # Also remove metadata file
                metadata_file = backup_file.with_suffix('.json').with_name(
                    backup_file.name.replace('backup_', 'metadata_').replace('.tar.gz', '.json')
                )
                if metadata_file.exists():
                    metadata_file.unlink()
        
        logger.info(f"Cleanup completed. Removed {removed_count} old backups.")
        return removed_count

def main():
    parser = argparse.ArgumentParser(description='Telecom Lab HA3 Backup and Restore Tool')
    parser.add_argument('--backup-dir', default='/opt/backups', help='Backup directory')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Create backup')
    backup_parser.add_argument('--type', choices=['full', 'config', 'database', 'monitoring'], 
                              default='full', help='Backup type')
    
    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('timestamp', help='Backup timestamp to restore')
    restore_parser.add_argument('--type', choices=['config', 'database'], 
                               required=True, help='Restore type')
    restore_parser.add_argument('--service', help='Specific service to restore (for config)')
    restore_parser.add_argument('--database', help='Specific database to restore')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available backups')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old backups')
    cleanup_parser.add_argument('--keep-days', type=int, default=30, 
                               help='Number of days to keep backups')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    backup_tool = TelecomBackup(args.backup_dir)
    
    if args.command == 'backup':
        if args.type == 'full':
            result = backup_tool.create_full_backup()
        elif args.type == 'config':
            timestamp = backup_tool.create_timestamp()
            result = backup_tool.backup_configurations(timestamp)
        elif args.type == 'database':
            timestamp = backup_tool.create_timestamp()
            result = backup_tool.backup_databases(timestamp)
        elif args.type == 'monitoring':
            timestamp = backup_tool.create_timestamp()
            result = backup_tool.backup_monitoring_data(timestamp)
        
        print(f"Backup completed. Results:")
        print(json.dumps(result, indent=2))
    
    elif args.command == 'restore':
        if args.type == 'config':
            success = backup_tool.restore_configuration(args.timestamp, args.service)
        elif args.type == 'database':
            success = backup_tool.restore_database(args.timestamp, args.database)
        
        if success:
            print("Restore completed successfully")
        else:
            print("Restore failed")
            sys.exit(1)
    
    elif args.command == 'list':
        backups = backup_tool.list_backups()
        
        if backups:
            print(f"{'Timestamp':<20} {'Type':<10} {'Hostname':<15} {'Size (MB)':<10}")
            print("-" * 65)
            for backup in backups:
                print(f"{backup['timestamp']:<20} {backup['backup_type']:<10} "
                      f"{backup['hostname']:<15} {backup['total_size_mb']:<10}")
        else:
            print("No backups found")
    
    elif args.command == 'cleanup':
        removed = backup_tool.cleanup_old_backups(args.keep_days)
        print(f"Removed {removed} old backup files")

if __name__ == '__main__':
    main()
