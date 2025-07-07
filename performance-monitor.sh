#!/bin/bash
# performance-monitor.sh - Performance monitor for telecom-lab-ha3

set -e

LOGFILE="/var/log/performance-monitor.log"
REPORT_DIR="/var/log/performance-reports"
DATA_DIR="/tmp/perf-data"

mkdir -p "$REPORT_DIR" "$DATA_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" | tee -a "$LOGFILE"
}

collect_system_metrics() {
    local output_file="$1"
    local duration="${2:-60}"  # seconds
    
    log "INFO" "Collecting system metrics for ${duration} seconds..."
    
    {
        echo "=== System Performance Report ==="
        echo "Generated: $(date)"
        echo "Duration: ${duration} seconds"
        echo "Hostname: $(hostname)"
        echo ""
        
        echo "=== CPU Information ==="
        lscpu
        echo ""
        
        echo "=== Memory Information ==="
        free -h
        echo ""
        
        echo "=== Disk Information ==="
        df -h
        echo ""
        
        echo "=== Network Interfaces ==="
        ip addr show
        echo ""
        
        echo "=== Load Average Monitoring ==="
        for i in $(seq 1 $((duration/5))); do
            echo "$(date '+%H:%M:%S') - $(uptime | awk -F'load average:' '{print $2}')"
            sleep 5
        done
        echo ""
        
        echo "=== Top Processes by CPU ==="
        ps aux --sort=-%cpu | head -20
        echo ""
        
        echo "=== Top Processes by Memory ==="
        ps aux --sort=-%mem | head -20
        echo ""
        
        echo "=== Network Statistics ==="
        ss -tuln
        echo ""
        
        echo "=== I/O Statistics ==="
        iostat -x 1 3 2>/dev/null || echo "iostat not available"
        echo ""
        
    } > "$output_file"
    
    log "INFO" "System metrics collected to: $output_file"
}

collect_sip_metrics() {
    local output_file="$1"
    
    log "INFO" "Collecting SIP metrics..."
    
    {
        echo "=== SIP Performance Metrics ==="
        echo "Generated: $(date)"
        echo ""
        
        echo "=== Kamailio Process Status ==="
        ps aux | grep kamailio | grep -v grep
        echo ""
        
        echo "=== SIP Port Statistics ==="
        ss -tulpen | grep :5060
        echo ""
        
        echo "=== SIP Connection Test ==="
        timeout 5 nc -zv 127.0.0.1 5060 2>&1 || echo "SIP port not responding"
        timeout 5 nc -zvu 127.0.0.1 5060 2>&1 || echo "SIP UDP port not responding"
        echo ""
        
        echo "=== Kamailio Statistics (if kamctl available) ==="
        if command -v kamctl >/dev/null 2>&1; then
            kamctl stats 2>/dev/null || echo "Could not retrieve kamctl stats"
        else
            echo "kamctl not available"
        fi
        echo ""
        
        echo "=== SIP Message Test ==="
        {
            echo "OPTIONS sip:127.0.0.1 SIP/2.0"
            echo "Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-test"
            echo "Max-Forwards: 70"
            echo "To: <sip:127.0.0.1>"
            echo "From: <sip:test@localhost>;tag=test123"
            echo "Call-ID: test@localhost"
            echo "CSeq: 1 OPTIONS"
            echo "Contact: <sip:test@localhost>"
            echo "Content-Length: 0"
            echo ""
        } | timeout 5 nc -u 127.0.0.1 5060 2>&1 || echo "SIP OPTIONS test failed"
        
    } > "$output_file"
    
    log "INFO" "SIP metrics collected to: $output_file"
}

collect_radius_metrics() {
    local output_file="$1"
    
    log "INFO" "Collecting RADIUS metrics..."
    
    {
        echo "=== RADIUS Performance Metrics ==="
        echo "Generated: $(date)"
        echo ""
        
        echo "=== FreeRADIUS Process Status ==="
        ps aux | grep freeradius | grep -v grep
        echo ""
        
        echo "=== RADIUS Port Statistics ==="
        ss -tulpen | grep -E ":(1812|1813)"
        echo ""
        
        echo "=== RADIUS Connection Test ==="
        timeout 5 nc -zvu 127.0.0.1 1812 2>&1 || echo "RADIUS auth port not responding"
        timeout 5 nc -zvu 127.0.0.1 1813 2>&1 || echo "RADIUS acct port not responding"
        echo ""
        
        echo "=== RADIUS Test Authentication ==="
        if command -v radtest >/dev/null 2>&1; then
            timeout 10 radtest testuser testpass 127.0.0.1 0 testing123 2>&1 || echo "RADIUS test failed"
        else
            echo "radtest not available"
        fi
        echo ""
        
        echo "=== FreeRADIUS Log Tail ==="
        tail -20 /var/log/freeradius/radius.log 2>/dev/null || echo "RADIUS log not accessible"
        
    } > "$output_file"
    
    log "INFO" "RADIUS metrics collected to: $output_file"
}

collect_galera_metrics() {
    local output_file="$1"
    
    log "INFO" "Collecting Galera cluster metrics..."
    
    {
        echo "=== Galera Cluster Performance Metrics ==="
        echo "Generated: $(date)"
        echo ""
        
        echo "=== MariaDB Process Status ==="
        ps aux | grep mysqld | grep -v grep
        echo ""
        
        echo "=== MySQL Connection Test ==="
        timeout 5 mysql -u root -e "SELECT 1;" 2>&1 || echo "MySQL connection failed"
        echo ""
        
        echo "=== Galera Cluster Status ==="
        mysql -u root -e "
            SHOW STATUS LIKE 'wsrep_cluster_size';
            SHOW STATUS LIKE 'wsrep_local_state_comment';
            SHOW STATUS LIKE 'wsrep_cluster_status';
            SHOW STATUS LIKE 'wsrep_connected';
            SHOW STATUS LIKE 'wsrep_ready';
        " 2>/dev/null || echo "Could not retrieve Galera status"
        echo ""
        
        echo "=== Galera Performance Status ==="
        mysql -u root -e "
            SHOW STATUS LIKE 'wsrep_flow_control_paused';
            SHOW STATUS LIKE 'wsrep_cert_deps_distance';
            SHOW STATUS LIKE 'wsrep_apply_oooe';
            SHOW STATUS LIKE 'wsrep_commit_oooe';
            SHOW STATUS LIKE 'wsrep_local_send_queue';
            SHOW STATUS LIKE 'wsrep_local_recv_queue';
        " 2>/dev/null || echo "Could not retrieve Galera performance status"
        echo ""
        
        echo "=== Database Sizes ==="
        mysql -u root -e "
            SELECT 
                table_schema AS 'Database',
                ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
            GROUP BY table_schema;
        " 2>/dev/null || echo "Could not retrieve database sizes"
        echo ""
        
        echo "=== InnoDB Status ==="
        mysql -u root -e "SHOW ENGINE INNODB STATUS\G" 2>/dev/null | head -50 || echo "Could not retrieve InnoDB status"
        
    } > "$output_file"
    
    log "INFO" "Galera metrics collected to: $output_file"
}

collect_monitoring_metrics() {
    local output_file="$1"
    
    log "INFO" "Collecting monitoring stack metrics..."
    
    {
        echo "=== Monitoring Stack Performance Metrics ==="
        echo "Generated: $(date)"
        echo ""
        
        echo "=== Docker Container Status ==="
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Size}}" 2>/dev/null || echo "Docker not available"
        echo ""
        
        echo "=== Prometheus Metrics Test ==="
        timeout 5 curl -s http://localhost:9090/metrics | head -20 2>/dev/null || echo "Prometheus metrics not accessible"
        echo ""
        
        echo "=== Grafana Health Check ==="
        timeout 5 curl -s http://localhost:3000/api/health 2>/dev/null || echo "Grafana health check failed"
        echo ""
        
        echo "=== Alertmanager Status ==="
        timeout 5 curl -s http://localhost:9093/api/v1/status 2>/dev/null || echo "Alertmanager not accessible"
        echo ""
        
        echo "=== Blackbox Exporter Test ==="
        timeout 5 curl -s http://localhost:9115/metrics | head -10 2>/dev/null || echo "Blackbox exporter not accessible"
        echo ""
        
        echo "=== Docker Resource Usage ==="
        docker stats --no-stream 2>/dev/null || echo "Docker stats not available"
        echo ""
        
        echo "=== Monitoring Volume Sizes ==="
        docker system df 2>/dev/null || echo "Docker system df not available"
        
    } > "$output_file"
    
    log "INFO" "Monitoring metrics collected to: $output_file"
}

generate_performance_report() {
    local duration="${1:-300}"  # Default 5 minutes
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local report_dir="$REPORT_DIR/perf_report_$timestamp"
    
    mkdir -p "$report_dir"
    
    log "INFO" "Generating comprehensive performance report..."
    
    # Collect all metrics in parallel
    collect_system_metrics "$report_dir/system_metrics.txt" "$duration" &
    collect_sip_metrics "$report_dir/sip_metrics.txt" &
    collect_radius_metrics "$report_dir/radius_metrics.txt" &
    collect_galera_metrics "$report_dir/galera_metrics.txt" &
    collect_monitoring_metrics "$report_dir/monitoring_metrics.txt" &
    
    # Wait for all background jobs to complete
    wait
    
    # Create summary report
    {
        echo "=============================================="
        echo "Telecom Lab HA3 Performance Summary Report"
        echo "=============================================="
        echo "Generated: $(date)"
        echo "Hostname: $(hostname)"
        echo "Duration: ${duration} seconds"
        echo ""
        
        echo "=== Quick System Overview ==="
        echo "Uptime: $(uptime)"
        echo "Load Average: $(uptime | awk -F'load average:' '{print $2}')"
        echo "Memory Usage: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
        echo "Disk Usage: $(df -h / | tail -1 | awk '{print $5}')"
        echo ""
        
        echo "=== Service Status Summary ==="
        for service in kamailio freeradius mariadb keepalived docker; do
            if systemctl is-active --quiet "$service"; then
                echo "✅ $service: RUNNING"
            else
                echo "❌ $service: STOPPED"
            fi
        done
        echo ""
        
        echo "=== Network Status Summary ==="
        if ip addr show | grep -q "192.168.56.254"; then
            echo "✅ VIP: ASSIGNED"
        else
            echo "❌ VIP: NOT ASSIGNED"
        fi
        
        for port in 5060 1812 1813 3306; do
            if ss -tulpen | grep -q ":$port"; then
                echo "✅ Port $port: LISTENING"
            else
                echo "❌ Port $port: NOT LISTENING"
            fi
        done
        echo ""
        
        echo "=== Galera Cluster Summary ==="
        if command -v mysql >/dev/null 2>&1; then
            cluster_size=$(mysql -u root -e "SHOW STATUS LIKE 'wsrep_cluster_size';" 2>/dev/null | grep wsrep_cluster_size | awk '{print $2}')
            node_state=$(mysql -u root -e "SHOW STATUS LIKE 'wsrep_local_state_comment';" 2>/dev/null | grep wsrep_local_state_comment | awk '{print $2}')
            
            echo "Cluster Size: ${cluster_size:-unknown}"
            echo "Node State: ${node_state:-unknown}"
        else
            echo "MySQL not accessible"
        fi
        echo ""
        
        echo "=== Report Files Generated ==="
        ls -la "$report_dir"/*.txt
        echo ""
        
        echo "=== Recommendations ==="
        
        # CPU check
        cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//' | cut -d. -f1)
        if [ "$cpu_usage" -gt 80 ]; then
            echo "⚠️  High CPU usage detected ($cpu_usage%). Consider load balancing."
        fi
        
        # Memory check
        mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
        if [ "$mem_usage" -gt 85 ]; then
            echo "⚠️  High memory usage detected ($mem_usage%). Consider adding RAM."
        fi
        
        # Disk check
        disk_usage=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
        if [ "$disk_usage" -gt 90 ]; then
            echo "⚠️  High disk usage detected ($disk_usage%). Clean up or add storage."
        fi
        
        echo "✅ Performance report completed."
        
    } > "$report_dir/performance_summary.txt"
    
    # Create compressed archive
    cd "$REPORT_DIR"
    tar -czf "perf_report_${timestamp}.tar.gz" "perf_report_$timestamp"
    rm -rf "perf_report_$timestamp"
    
    log "INFO" "Performance report created: $REPORT_DIR/perf_report_${timestamp}.tar.gz"
    echo "Performance report saved to: $REPORT_DIR/perf_report_${timestamp}.tar.gz"
}

continuous_monitoring() {
    local interval="${1:-60}"  # seconds
    local duration="${2:-3600}"  # total duration in seconds
    
    log "INFO" "Starting continuous monitoring (interval: ${interval}s, duration: ${duration}s)"
    
    local end_time=$(($(date +%s) + duration))
    local monitor_file="$DATA_DIR/continuous_monitor_$(date +%Y%m%d_%H%M%S).log"
    
    {
        echo "Timestamp,CPU_Usage,Memory_Usage,Load_1min,SIP_Port,RADIUS_Port,Galera_Size"
        
        while [ $(date +%s) -lt $end_time ]; do
            timestamp=$(date '+%Y-%m-%d %H:%M:%S')
            cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
            mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
            load_1min=$(uptime | awk -F'load average:' '{print $2}' | awk -F, '{print $1}' | xargs)
            
            # Check SIP port
            if ss -tulpen | grep -q ":5060"; then
                sip_status="UP"
            else
                sip_status="DOWN"
            fi
            
            # Check RADIUS port
            if ss -tulpen | grep -q ":1812"; then
                radius_status="UP"
            else
                radius_status="DOWN"
            fi
            
            # Check Galera cluster size
            if command -v mysql >/dev/null 2>&1; then
                galera_size=$(mysql -u root -e "SHOW STATUS LIKE 'wsrep_cluster_size';" 2>/dev/null | grep wsrep_cluster_size | awk '{print $2}' || echo "unknown")
            else
                galera_size="unknown"
            fi
            
            echo "$timestamp,$cpu_usage,$mem_usage,$load_1min,$sip_status,$radius_status,$galera_size"
            
            sleep "$interval"
        done
        
    } > "$monitor_file"
    
    log "INFO" "Continuous monitoring completed. Data saved to: $monitor_file"
    echo "Monitoring data saved to: $monitor_file"
}

# Main function
main() {
    case "${1:-report}" in
        "report")
            duration="${2:-300}"
            generate_performance_report "$duration"
            ;;
        "system")
            output_file="${2:-$DATA_DIR/system_metrics_$(date +%Y%m%d_%H%M%S).txt}"
            duration="${3:-60}"
            collect_system_metrics "$output_file" "$duration"
            ;;
        "sip")
            output_file="${2:-$DATA_DIR/sip_metrics_$(date +%Y%m%d_%H%M%S).txt}"
            collect_sip_metrics "$output_file"
            ;;
        "radius")
            output_file="${2:-$DATA_DIR/radius_metrics_$(date +%Y%m%d_%H%M%S).txt}"
            collect_radius_metrics "$output_file"
            ;;
        "galera")
            output_file="${2:-$DATA_DIR/galera_metrics_$(date +%Y%m%d_%H%M%S).txt}"
            collect_galera_metrics "$output_file"
            ;;
        "monitoring")
            output_file="${2:-$DATA_DIR/monitoring_metrics_$(date +%Y%m%d_%H%M%S).txt}"
            collect_monitoring_metrics "$output_file"
            ;;
        "continuous")
            interval="${2:-60}"
            duration="${3:-3600}"
            continuous_monitoring "$interval" "$duration"
            ;;
        *)
            echo "Usage: $0 {report|system|sip|radius|galera|monitoring|continuous} [options]"
            echo ""
            echo "Commands:"
            echo "  report [duration]              - Generate comprehensive performance report (default: 300s)"
            echo "  system [output_file] [duration] - Collect system metrics"
            echo "  sip [output_file]              - Collect SIP metrics"
            echo "  radius [output_file]           - Collect RADIUS metrics"
            echo "  galera [output_file]           - Collect Galera cluster metrics"
            echo "  monitoring [output_file]       - Collect monitoring stack metrics"
            echo "  continuous [interval] [duration] - Continuous monitoring (default: 60s interval, 3600s total)"
            echo ""
            echo "Examples:"
            echo "  $0 report 600                  - 10-minute performance report"
            echo "  $0 continuous 30 1800         - Monitor every 30s for 30 minutes"
            echo "  $0 system /tmp/sys.txt 120     - Collect system metrics for 2 minutes"
            exit 1
            ;;
    esac
}

main "$@"
