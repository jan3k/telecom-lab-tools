#!/usr/bin/env python3
"""
sip_radius_diagnostics.py - Advanced SIP and RADIUS diagnostics for telecom-lab-ha3
"""

import socket
import subprocess
import json
import time
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/sip-radius-diagnostics.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelecomDiagnostics:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'hostname': socket.gethostname(),
            'tests': {}
        }
        
    def test_sip_connectivity(self, host: str = '127.0.0.1', port: int = 5060) -> Dict:
        """Test SIP server connectivity and basic response"""
        logger.info(f"Testing SIP connectivity to {host}:{port}")
        
        result = {
            'test': 'sip_connectivity',
            'target': f"{host}:{port}",
            'status': 'unknown',
            'response_time': None,
            'details': {}
        }
        
        try:
            # TCP connectivity test
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            tcp_result = sock.connect_ex((host, port))
            sock.close()
            
            if tcp_result == 0:
                result['details']['tcp_connectivity'] = 'OK'
            else:
                result['details']['tcp_connectivity'] = 'FAILED'
                result['status'] = 'failed'
                return result
            
            # UDP SIP OPTIONS test
            sip_message = (
                f"OPTIONS sip:{host} SIP/2.0\r\n"
                f"Via: SIP/2.0/UDP {socket.gethostname()}:5060;branch=z9hG4bK-diag-{int(time.time())}\r\n"
                f"Max-Forwards: 70\r\n"
                f"To: <sip:{host}>\r\n"
                f"From: <sip:diagnostic@{socket.gethostname()}>;tag=diag123\r\n"
                f"Call-ID: diagnostic-{int(time.time())}@{socket.gethostname()}\r\n"
                f"CSeq: 1 OPTIONS\r\n"
                f"Contact: <sip:diagnostic@{socket.gethostname()}>\r\n"
                f"User-Agent: TelecomDiagnostics/1.0\r\n"
                f"Content-Length: 0\r\n\r\n"
            )
            
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.settimeout(5)
            udp_sock.sendto(sip_message.encode(), (host, port))
            
            try:
                response, addr = udp_sock.recvfrom(4096)
                end_time = time.time()
                response_time = (end_time - start_time) * 1000
                
                result['response_time'] = round(response_time, 2)
                result['details']['sip_response'] = response.decode('utf-8', errors='ignore')[:200]
                
                if b'SIP/2.0' in response:
                    result['status'] = 'passed'
                    result['details']['sip_status'] = 'Valid SIP response received'
                else:
                    result['status'] = 'warning'
                    result['details']['sip_status'] = 'Invalid SIP response'
                    
            except socket.timeout:
                result['status'] = 'failed'
                result['details']['sip_status'] = 'SIP response timeout'
                
            udp_sock.close()
            
        except Exception as e:
            result['status'] = 'error'
            result['details']['error'] = str(e)
            logger.error(f"SIP test error: {e}")
            
        return result
    
    def test_radius_auth(self, host: str = '127.0.0.1', port: int = 1812, 
                        username: str = 'testuser', password: str = 'testpass',
                        secret: str = 'testing123') -> Dict:
        """Test RADIUS authentication"""
        logger.info(f"Testing RADIUS authentication to {host}:{port}")
        
        result = {
            'test': 'radius_auth',
            'target': f"{host}:{port}",
            'username': username,
            'status': 'unknown',
            'response_time': None,
            'details': {}
        }
        
        try:
            # Use radtest command if available
            start_time = time.time()
            cmd = [
                'radtest', username, password, host, '0', secret
            ]
            
            process = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            end_time = time.time()
            result['response_time'] = round((end_time - start_time) * 1000, 2)
            result['details']['command_output'] = process.stdout
            result['details']['command_error'] = process.stderr
            result['details']['return_code'] = process.returncode
            
            if 'Access-Accept' in process.stdout:
                result['status'] = 'passed'
                result['details']['auth_result'] = 'Access-Accept'
            elif 'Access-Reject' in process.stdout:
                result['status'] = 'passed'  # Server responded, auth rejected
                result['details']['auth_result'] = 'Access-Reject'
            elif process.returncode == 0:
                result['status'] = 'passed'
                result['details']['auth_result'] = 'Server responded'
            else:
                result['status'] = 'failed'
                result['details']['auth_result'] = 'No response or error'
                
        except subprocess.TimeoutExpired:
            result['status'] = 'failed'
            result['details']['auth_result'] = 'Timeout'
        except FileNotFoundError:
            result['status'] = 'error'
            result['details']['auth_result'] = 'radtest command not found'
        except Exception as e:
            result['status'] = 'error'
            result['details']['error'] = str(e)
            logger.error(f"RADIUS test error: {e}")
            
        return result
    
    def test_galera_cluster(self) -> Dict:
        """Test MariaDB Galera cluster status"""
        logger.info("Testing Galera cluster status")
        
        result = {
            'test': 'galera_cluster',
            'status': 'unknown',
            'details': {}
        }
        
        try:
            # Check cluster size
            cmd = ['mysql', '-u', 'root', '-e', "SHOW STATUS LIKE 'wsrep_cluster_size';"]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if process.returncode == 0:
                lines = process.stdout.strip().split('\n')
                for line in lines:
                    if 'wsrep_cluster_size' in line:
                        cluster_size = int(line.split('\t')[1])
                        result['details']['cluster_size'] = cluster_size
                        
                        if cluster_size == 3:
                            result['details']['cluster_size_status'] = 'OK'
                        else:
                            result['details']['cluster_size_status'] = f'WARNING: Expected 3, got {cluster_size}'
            
            # Check local state
            cmd = ['mysql', '-u', 'root', '-e', "SHOW STATUS LIKE 'wsrep_local_state_comment';"]
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if process.returncode == 0:
                lines = process.stdout.strip().split('\n')
                for line in lines:
                    if 'wsrep_local_state_comment' in line:
                        state = line.split('\t')[1]
                        result['details']['local_state'] = state
                        
                        if state == 'Synced':
                            result['details']['local_state_status'] = 'OK'
                        else:
                            result['details']['local_state_status'] = f'WARNING: State is {state}'
            
            # Determine overall status
            cluster_ok = result['details'].get('cluster_size', 0) == 3
            state_ok = result['details'].get('local_state') == 'Synced'
            
            if cluster_ok and state_ok:
                result['status'] = 'passed'
            elif cluster_ok or state_ok:
                result['status'] = 'warning'
            else:
                result['status'] = 'failed'
                
        except Exception as e:
            result['status'] = 'error'
            result['details']['error'] = str(e)
            logger.error(f"Galera test error: {e}")
            
        return result
    
    def test_monitoring_endpoints(self) -> Dict:
        """Test monitoring system endpoints"""
        logger.info("Testing monitoring endpoints")
        
        result = {
            'test': 'monitoring_endpoints',
            'status': 'unknown',
            'details': {}
        }
        
        endpoints = {
            'prometheus': ('localhost', 9090, '/metrics'),
            'grafana': ('localhost', 3000, '/api/health'),
            'alertmanager': ('localhost', 9093, '/api/v1/status'),
            'blackbox': ('localhost', 9115, '/metrics'),
            'node_exporter': ('localhost', 9100, '/metrics')
        }
        
        passed_count = 0
        total_count = len(endpoints)
        
        for service, (host, port, path) in endpoints.items():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                connection_result = sock.connect_ex((host, port))
                sock.close()
                
                if connection_result == 0:
                    result['details'][f'{service}_port'] = 'OK'
                    passed_count += 1
                else:
                    result['details'][f'{service}_port'] = 'FAILED'
                    
            except Exception as e:
                result['details'][f'{service}_port'] = f'ERROR: {e}'
        
        # Determine overall status
        if passed_count == total_count:
            result['status'] = 'passed'
        elif passed_count > total_count / 2:
            result['status'] = 'warning'
        else:
            result['status'] = 'failed'
            
        result['details']['summary'] = f"{passed_count}/{total_count} endpoints accessible"
        
        return result
    
    def run_comprehensive_test(self, targets: Optional[List[str]] = None) -> Dict:
        """Run comprehensive diagnostic tests"""
        logger.info("Starting comprehensive diagnostic tests")
        
        if not targets:
            targets = ['127.0.0.1', '192.168.56.254']  # localhost and VIP
        
        # SIP tests
        for target in targets:
            test_name = f"sip_test_{target.replace('.', '_')}"
            self.results['tests'][test_name] = self.test_sip_connectivity(target)
        
        # RADIUS tests  
        for target in targets:
            test_name = f"radius_test_{target.replace('.', '_')}"
            self.results['tests'][test_name] = self.test_radius_auth(target)
        
        # Galera cluster test
        self.results['tests']['galera_cluster'] = self.test_galera_cluster()
        
        # Monitoring endpoints test
        self.results['tests']['monitoring_endpoints'] = self.test_monitoring_endpoints()
        
        # Summary
        passed = sum(1 for test in self.results['tests'].values() if test['status'] == 'passed')
        warning = sum(1 for test in self.results['tests'].values() if test['status'] == 'warning')
        failed = sum(1 for test in self.results['tests'].values() if test['status'] == 'failed')
        error = sum(1 for test in self.results['tests'].values() if test['status'] == 'error')
        total = len(self.results['tests'])
        
        self.results['summary'] = {
            'total_tests': total,
            'passed': passed,
            'warning': warning,
            'failed': failed,
            'error': error,
            'success_rate': round((passed / total) * 100, 1) if total > 0 else 0
        }
        
        logger.info(f"Tests completed: {passed}/{total} passed, {warning} warnings, {failed} failed")
        
        return self.results
    
    def generate_report(self, output_file: str = None) -> str:
        """Generate diagnostic report"""
        if not output_file:
            output_file = f"/var/log/diagnostics-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Diagnostic report saved to: {output_file}")
        return output_file

def main():
    parser = argparse.ArgumentParser(description='Telecom Lab HA3 Diagnostics Tool')
    parser.add_argument('--targets', nargs='+', default=['127.0.0.1', '192.168.56.254'],
                       help='Target hosts to test')
    parser.add_argument('--test', choices=['sip', 'radius', 'galera', 'monitoring', 'all'],
                       default='all', help='Test type to run')
    parser.add_argument('--output', help='Output file for results')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    
    args = parser.parse_args()
    
    diagnostics = TelecomDiagnostics()
    
    if args.test == 'all':
        results = diagnostics.run_comprehensive_test(args.targets)
    elif args.test == 'sip':
        for target in args.targets:
            test_name = f"sip_test_{target.replace('.', '_')}"
            diagnostics.results['tests'][test_name] = diagnostics.test_sip_connectivity(target)
    elif args.test == 'radius':
        for target in args.targets:
            test_name = f"radius_test_{target.replace('.', '_')}"
            diagnostics.results['tests'][test_name] = diagnostics.test_radius_auth(target)
    elif args.test == 'galera':
        diagnostics.results['tests']['galera_cluster'] = diagnostics.test_galera_cluster()
    elif args.test == 'monitoring':
        diagnostics.results['tests']['monitoring_endpoints'] = diagnostics.test_monitoring_endpoints()
    
    if args.json:
        print(json.dumps(diagnostics.results, indent=2))
    else:
        # Pretty print summary
        print(f"\n=== Telecom Lab HA3 Diagnostics ===")
        print(f"Timestamp: {diagnostics.results['timestamp']}")
        print(f"Hostname: {diagnostics.results['hostname']}")
        print(f"\nTest Results:")
        
        for test_name, test_result in diagnostics.results['tests'].items():
            status_emoji = {
                'passed': '✅',
                'warning': '⚠️',
                'failed': '❌',
                'error': '💥',
                'unknown': '❓'
            }.get(test_result['status'], '❓')
            
            print(f"  {status_emoji} {test_name}: {test_result['status'].upper()}")
            
            if test_result.get('response_time'):
                print(f"    Response time: {test_result['response_time']}ms")
            
            if test_result['status'] in ['failed', 'error', 'warning']:
                for key, value in test_result.get('details', {}).items():
                    if 'error' in key.lower() or 'status' in key.lower():
                        print(f"    {key}: {value}")
    
    if args.output:
        diagnostics.generate_report(args.output)

if __name__ == '__main__':
    main()
