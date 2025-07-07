#!/bin/bash
# service-manager.sh - managing of telecom-lab-ha3 services

set -e

LOGFILE="/var/log/service-manager.log"
SERVICES=("kamailio" "freeradius" "mariadb" "keepalived" "puppet" "docker")
MONITORING_SERVICES=("prometheus" "grafana" "alertmanager")

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" | tee -a "$LOGFILE"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi
}

service_status() {
    local service="$1"
    if systemctl is-active --quiet "$service"; then
        echo "RUNNING"
    else
        echo "STOPPED"
    fi
}

service_enabled() {
    local service="$1"
    if systemctl is-enabled --quiet "$service"; then
        echo "ENABLED"
    else
        echo "DISABLED"
    fi
}

start_service() {
    local service="$1"
    log "INFO" "Starting service: $service"
    
    if systemctl start "$service"; then
        log "INFO" "Service $service started successfully"
        return 0
    else
        log "ERROR" "Failed to start service: $service"
        return 1
    fi
}

stop_service() {
    local service="$1"
    log "INFO" "Stopping service: $service"
    
    if systemctl stop "$service"; then
        log "INFO" "Service $service stopped successfully"
        return 0
    else
        log "ERROR" "Failed to stop service: $service"
        return 1
    fi
}

restart_service() {
    local service="$1"
    log "INFO" "Restarting service: $service"
    
    if systemctl restart "$service"; then
        log "INFO" "Service $service restarted successfully"
        return 0
    else
        log "ERROR" "Failed to restart service: $service"
        return 1
    fi
}

enable_service() {
    local service="$1"
    log "INFO" "Enabling service: $service"
    
    if systemctl enable "$service"; then
        log "INFO" "Service $service enabled successfully"
        return 0
    else
        log "ERROR" "Failed to enable service: $service"
        return 1
    fi
}

show_status() {
    echo "=== Telecom Lab HA3 Service Status ==="
    echo "Generated: $(date)"
    echo ""
    
    printf "%-15s %-10s %-10s %-15s\n" "SERVICE" "STATUS" "ENABLED" "DESCRIPTION"
    printf "%-15s %-10s %-10s %-15s\n" "-------" "------" "-------" "-----------"
    
    for service in "${SERVICES[@]}"; do
        status=$(service_status "$service")
        enabled=$(service_enabled "$service")
        
        case "$service" in
            "kamailio") desc="SIP Server" ;;
            "freeradius") desc="RADIUS Server" ;;
            "mariadb") desc="Database" ;;
            "keepalived") desc="HA/VIP Manager" ;;
            "puppet") desc="Config Management" ;;
            "docker") desc="Container Runtime" ;;
            *) desc="Unknown" ;;
        esac
        
        printf "%-15s %-10s %-10s %-15s\n" "$service" "$status" "$enabled" "$desc"
    done
    
    echo ""
    echo "=== Docker Container Status ==="
    if systemctl is-active --quiet docker; then
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No containers running"
    else
        echo "Docker service is not running"
    fi
}

start_all() {
    log "INFO" "Starting all telecom services..."
    failed_services=()
    
    for service in "${SERVICES[@]}"; do
        if ! start_service "$service"; then
            failed_services+=("$service")
        fi
        sleep 2
    done
    
    # Start monitoring stack
    if systemctl is-active --quiet docker; then
        log "INFO" "Starting monitoring stack..."
        cd /opt/monitoring && docker-compose up -d 2>/dev/null || log "WARN" "Failed to start monitoring stack"
    fi
    
    if [ ${#failed_services[@]} -eq 0 ]; then
        log "INFO" "All services started successfully"
        return 0
    else
        log "ERROR" "Failed to start services: ${failed_services[*]}"
        return 1
    fi
}

stop_all() {
    log "INFO" "Stopping all telecom services..."
    failed_services=()
    
    # Stop monitoring stack first
    if systemctl is-active --quiet docker; then
        log "INFO" "Stopping monitoring stack..."
        cd /opt/monitoring && docker-compose down 2>/dev/null || log "WARN" "Failed to stop monitoring stack"
    fi
    
    # Stop services in reverse order
    for ((i=${#SERVICES[@]}-1; i>=0; i--)); do
        service="${SERVICES[$i]}"
        if ! stop_service "$service"; then
            failed_services+=("$service")
        fi
        sleep 2
    done
    
    if [ ${#failed_services[@]} -eq 0 ]; then
        log "INFO" "All services stopped successfully"
        return 0
    else
        log "ERROR" "Failed to stop services: ${failed_services[*]}"
        return 1
    fi
}

restart_all() {
    log "INFO" "Restarting all telecom services..."
    stop_all
    sleep 5
    start_all
}

bootstrap_galera() {
    log "INFO" "Bootstrapping Galera cluster..."
    
    # Stop MariaDB on all nodes
    stop_service "mariadb"
    
    # Start bootstrap on current node
    log "INFO" "Starting Galera bootstrap on $(hostname)"
    if galera_new_cluster; then
        log "INFO" "Galera bootstrap successful"
        return 0
    else
        log "ERROR" "Galera bootstrap failed"
        return 1
    fi
}

failover_test() {
    log "INFO" "Running failover test..."
    
    # Get current VIP holder
    current_vip_holder=$(ip addr show | grep "192.168.56.254" && hostname || echo "none")
    log "INFO" "Current VIP holder: $current_vip_holder"
    
    # Stop keepalived to trigger failover
    log "INFO" "Stopping keepalived to trigger failover..."
    stop_service "keepalived"
    
    sleep 10
    
    # Check VIP status
    if ip addr show | grep -q "192.168.56.254"; then
        log "WARN" "VIP still assigned to this node after failover test"
    else
        log "INFO" "VIP failover successful - VIP moved to another node"
    fi
    
    # Restart keepalived
    start_service "keepalived"
    
    sleep 5
    
    # Final VIP check
    new_vip_holder=$(ip addr show | grep "192.168.56.254" && hostname || echo "none")
    log "INFO" "Final VIP holder: $new_vip_holder"
}

check_dependencies() {
    log "INFO" "Checking service dependencies..."
    
    # Check if services are properly ordered
    dependencies=(
        "mariadb:before keepalived"
        "docker:before monitoring"
        "puppet:independent"
    )
    
    for dep in "${dependencies[@]}"; do
        service=$(echo "$dep" | cut -d: -f1)
        requirement=$(echo "$dep" | cut -d: -f2-)
        
        status=$(service_status "$service")
        log "INFO" "Service $service ($requirement): $status"
    done
}

show_logs() {
    local service="$1"
    local lines="${2:-50}"
    
    if [ -z "$service" ]; then
        echo "Available services for log viewing:"
        printf "%s\n" "${SERVICES[@]}"
        return 1
    fi
    
    echo "=== Last $lines lines of $service logs ==="
    journalctl -u "$service" -n "$lines" --no-pager
}

maintenance_mode() {
    local action="$1"
    
    case "$action" in
        "enable")
            log "INFO" "Enabling maintenance mode..."
            
            # Create maintenance flag
            touch /var/lib/telecom-lab/maintenance
            
            # Stop non-essential services
            for service in kamailio freeradius; do
                stop_service "$service"
            done
            
            log "INFO" "Maintenance mode enabled - SIP/RADIUS services stopped"
            ;;
        "disable")
            log "INFO" "Disabling maintenance mode..."
            
            # Remove maintenance flag
            rm -f /var/lib/telecom-lab/maintenance
            
            # Start services
            for service in kamailio freeradius; do
                start_service "$service"
            done
            
            log "INFO" "Maintenance mode disabled - services restored"
            ;;
        "status")
            if [ -f /var/lib/telecom-lab/maintenance ]; then
                echo "Maintenance mode: ENABLED"
                echo "Created: $(stat -c %y /var/lib/telecom-lab/maintenance)"
            else
                echo "Maintenance mode: DISABLED"
            fi
            ;;
        *)
            echo "Usage: $0 maintenance [enable|disable|status]"
            return 1
            ;;
    esac
}

# Główna funkcja
main() {
    case "${1:-status}" in
        "status"|"")
            show_status
            ;;
        "start")
            check_root
            if [ -n "$2" ]; then
                start_service "$2"
            else
                start_all
            fi
            ;;
        "stop")
            check_root
            if [ -n "$2" ]; then
                stop_service "$2"
            else
                stop_all
            fi
            ;;
        "restart")
            check_root
            if [ -n "$2" ]; then
                restart_service "$2"
            else
                restart_all
            fi
            ;;
        "enable")
            check_root
            enable_service "$2"
            ;;
        "bootstrap-galera")
            check_root
            bootstrap_galera
            ;;
        "failover-test")
            check_root
            failover_test
            ;;
        "dependencies")
            check_dependencies
            ;;
        "logs")
            show_logs "$2" "$3"
            ;;
        "maintenance")
            check_root
            maintenance_mode "$2"
            ;;
        *)
            echo "Usage: $0 {status|start|stop|restart|enable|bootstrap-galera|failover-test|dependencies|logs|maintenance} [service] [options]"
            echo ""
            echo "Commands:"
            echo "  status              - Show service status"
            echo "  start [service]     - Start service(s)"
            echo "  stop [service]      - Stop service(s)"
            echo "  restart [service]   - Restart service(s)"
            echo "  enable <service>    - Enable service"
            echo "  bootstrap-galera    - Bootstrap Galera cluster"
            echo "  failover-test       - Test VIP failover"
            echo "  dependencies        - Check service dependencies"
            echo "  logs <service> [n]  - Show service logs (last n lines)"
            echo "  maintenance [action] - Enable/disable maintenance mode"
            echo ""
            echo "Available services: ${SERVICES[*]}"
            exit 1
            ;;
    esac
}

main "$@"
