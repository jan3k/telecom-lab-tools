#!/bin/bash
# health-check.sh - health check for telecom-lab-ha3

set -e

LOGFILE="/var/log/telecom-health.log"
EMAIL="admin@telecom-lab-ha3.local"
THRESHOLD_CPU=80
THRESHOLD_MEM=85
THRESHOLD_DISK=90

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" | tee -a "$LOGFILE"
}

check_system_resources() {
    log "INFO" "=== System Resources Check ==="
    
    # CPU Usage
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    CPU_NUM=${CPU_USAGE%.*}
    if [ "$CPU_NUM" -gt "$THRESHOLD_CPU" ]; then
        log "WARN" "High CPU usage: ${CPU_USAGE}%"
        ALERTS="$ALERTS\nHigh CPU usage: ${CPU_USAGE}%"
    else
        log "INFO" "CPU usage OK: ${CPU_USAGE}%"
    fi
    
    # Memory Usage
    MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    MEM_NUM=${MEM_USAGE%.*}
    if [ "$MEM_NUM" -gt "$THRESHOLD_MEM" ]; then
        log "WARN" "High memory usage: ${MEM_USAGE}%"
        ALERTS="$ALERTS\nHigh memory usage: ${MEM_USAGE}%"
    else
        log "INFO" "Memory usage OK: ${MEM_USAGE}%"
    fi
    
    # Disk Usage
    while read -r line; do
        USAGE=$(echo "$line" | awk '{print $5}' | sed 's/%//')
        MOUNT=$(echo "$line" | awk '{print $6}')
        if [ "$USAGE" -gt "$THRESHOLD_DISK" ]; then
            log "WARN" "High disk usage on $MOUNT: ${USAGE}%"
            ALERTS="$ALERTS\nHigh disk usage on $MOUNT: ${USAGE}%"
        else
            log "INFO" "Disk usage OK on $MOUNT: ${USAGE}%"
        fi
    done < <(df -h | grep -E "^/dev" | grep -v tmpfs)
}

check_services() {
    log "INFO" "=== Services Check ==="
    
    SERVICES=("kamailio" "freeradius" "mariadb" "keepalived" "puppet" "docker")
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            log "INFO" "Service $service is running"
        else
            log "ERROR" "Service $service is NOT running"
            ALERTS="$ALERTS\nService $service is DOWN"
        fi
    done
}

check_network() {
    log "INFO" "=== Network Check ==="
    
    # Check VIP
    if ip addr show | grep -q "192.168.56.254"; then
        log "INFO" "VIP 192.168.56.254 is assigned"
    else
        log "WARN" "VIP 192.168.56.254 is NOT assigned"
        ALERTS="$ALERTS\nVIP not assigned"
    fi
    
    # Check connectivity to other nodes
    NODES=("ha1.lab.local" "ha2.lab.local" "ha3.lab.local" "puppet.lab.local" "jumphost.lab.local")
    
    for node in "${NODES[@]}"; do
        if ping -c1 -W2 "$node" >/dev/null 2>&1; then
            log "INFO" "Connectivity to $node OK"
        else
            log "ERROR" "Cannot reach $node"
            ALERTS="$ALERTS\nCannot reach $node"
        fi
    done
}

check_galera_cluster() {
    log "INFO" "=== Galera Cluster Check ==="
    
    if command -v mysql >/dev/null 2>&1; then
        CLUSTER_SIZE=$(mysql -u root -e "SHOW STATUS LIKE 'wsrep_cluster_size';" 2>/dev/null | grep wsrep_cluster_size | awk '{print $2}')
        NODE_STATE=$(mysql -u root -e "SHOW STATUS LIKE 'wsrep_local_state_comment';" 2>/dev/null | grep wsrep_local_state_comment | awk '{print $2}')
        
        if [ "$CLUSTER_SIZE" = "3" ]; then
            log "INFO" "Galera cluster size OK: $CLUSTER_SIZE nodes"
        else
            log "ERROR" "Galera cluster size issue: $CLUSTER_SIZE nodes (expected 3)"
            ALERTS="$ALERTS\nGalera cluster size: $CLUSTER_SIZE (expected 3)"
        fi
        
        if [ "$NODE_STATE" = "Synced" ]; then
            log "INFO" "Galera node state OK: $NODE_STATE"
        else
            log "WARN" "Galera node state: $NODE_STATE (expected Synced)"
            ALERTS="$ALERTS\nGalera node state: $NODE_STATE"
        fi
    else
        log "WARN" "MySQL client not available for Galera check"
    fi
}

check_sip_radius() {
    log "INFO" "=== SIP/RADIUS Check ==="
    
    # SIP port check
    if ss -tulpen | grep -q ":5060"; then
        log "INFO" "SIP port 5060 is listening"
    else
        log "ERROR" "SIP port 5060 is NOT listening"
        ALERTS="$ALERTS\nSIP port not listening"
    fi
    
    # RADIUS ports check
    if ss -tulpen | grep -q ":1812"; then
        log "INFO" "RADIUS auth port 1812 is listening"
    else
        log "ERROR" "RADIUS auth port 1812 is NOT listening"
        ALERTS="$ALERTS\nRADIUS auth port not listening"
    fi
    
    if ss -tulpen | grep -q ":1813"; then
        log "ERROR" "RADIUS acct port 1813 is listening"
    else
        log "ERROR" "RADIUS acct port 1813 is NOT listening"
        ALERTS="$ALERTS\nRADIUS acct port not listening"
    fi
}

send_alerts() {
    if [ -n "$ALERTS" ]; then
        log "ERROR" "Sending alerts..."
        echo -e "Health check alerts for $(hostname) at $(date):\n$ALERTS" | \
        mail -s "Telecom Lab HA3 Health Alert - $(hostname)" "$EMAIL" 2>/dev/null || \
        log "ERROR" "Failed to send email alert"
    else
        log "INFO" "No alerts to send - all checks passed"
    fi
}

generate_report() {
    REPORT_FILE="/var/log/health-report-$(date +%Y%m%d-%H%M%S).txt"
    
    {
        echo "============================================"
        echo "Telecom Lab HA3 Health Report"
        echo "Generated: $(date)"
        echo "Hostname: $(hostname)"
        echo "============================================"
        echo ""
        
        echo "System Information:"
        echo "- Uptime: $(uptime)"
        echo "- Load Average: $(uptime | awk -F'load average:' '{print $2}')"
        echo "- Memory: $(free -h | grep Mem)"
        echo "- Disk: $(df -h | grep -E '^/dev')"
        echo ""
        
        echo "Service Status:"
        for service in kamailio freeradius mariadb keepalived puppet docker; do
            if systemctl is-active --quiet "$service"; then
                echo "- $service: RUNNING"
            else
                echo "- $service: STOPPED"
            fi
        done
        echo ""
        
        echo "Network Status:"
        echo "- VIP Status: $(ip addr show | grep -q "192.168.56.254" && echo "ASSIGNED" || echo "NOT ASSIGNED")"
        echo "- Open Ports:"
        ss -tulpen | grep LISTEN
        echo ""
        
        if [ -n "$ALERTS" ]; then
            echo "ALERTS:"
            echo -e "$ALERTS"
        else
            echo "✅ All checks passed - no alerts"
        fi
        
    } > "$REPORT_FILE"
    
    log "INFO" "Health report saved to: $REPORT_FILE"
}

main() {
    log "INFO" "Starting health check for $(hostname)"
    
    ALERTS=""
    
    check_system_resources
    check_services
    check_network
    check_galera_cluster
    check_sip_radius
    
    generate_report
    send_alerts
    
    log "INFO" "Health check completed"
}

# Uruchomienie z argumentami
case "${1:-check}" in
    "check"|"")
        main
        ;;
    "services")
        check_services
        ;;
    "network")
        check_network
        ;;
    "galera")
        check_galera_cluster
        ;;
    "report")
        generate_report
        ;;
    *)
        echo "Usage: $0 [check|services|network|galera|report]"
        exit 1
        ;;
esac
