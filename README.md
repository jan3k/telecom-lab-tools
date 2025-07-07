# Dokumentacja skryptów zarządzania Telecom Lab HA3

Dokumentacja dla kluczowych skryptów operacyjnych i diagnostycznych projektu telecom-lab-ha3.

## 📋 Spis treści

1. [backup_restore.py](#backup_restorepy)
2. [health-check.sh](#health-checksh)
3. [maintenance.py](#maintenancepy)
4. [performance-monitor.sh](#performance-monitorsh)
5. [service-manager.sh](#service-managersh)
6. [sip_radius_diagnostics.py](#sip_radius_diagnosticspy)

## backup_restore.py

### Opis
Zaawansowany skrypt Python do zarządzania backupami i przywracaniem danych w środowisku telecom-lab-ha3. Obsługuje backup baz danych MySQL/Galera, konfiguracji usług oraz pełnego systemu.

### Funkcjonalności
- **Backup automatyczny** - MySQL/Galera, konfiguracje, logi
- **Przywracanie selektywne** - wybrane komponenty lub pełny system
- **Kompresja i szyfrowanie** - backup'y zabezpieczone hasłem
- **Rotacja backup'ów** - automatyczne usuwanie starych kopii
- **Weryfikacja integralności** - sprawdzanie poprawności backup'ów

### Składnia
```bash
python3 backup_restore.py [OPCJE] [KOMENDA]
```

### Parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `--backup` | Tworzy backup | `--backup mysql` |
| `--restore` | Przywraca z backup | `--restore mysql` |
| `--list` | Lista dostępnych backup'ów | `--list` |
| `--verify` | Weryfikuje backup | `--verify backup.tar.gz` |
| `--encrypt` | Szyfruje backup | `--encrypt --password secret` |
| `--config` | Plik konfiguracyjny | `--config /etc/backup.conf` |

### Przykłady użycia

#### Backup pełnego systemu
```bash
python3 backup_restore.py --backup full --encrypt --password "SecretPass123"
```

#### Backup tylko bazy danych
```bash
python3 backup_restore.py --backup mysql --compress
```

#### Przywracanie konfiguracji
```bash
python3 backup_restore.py --restore config --from backup_20240101_120000.tar.gz
```

#### Lista backup'ów
```bash
python3 backup_restore.py --list --verbose
```

### Konfiguracja

Plik `/etc/telecom-lab/backup.conf`:
```json
{
    "backup_dir": "/opt/backups",
    "retention_days": 30,
    "compression": true,
    "encryption": true,
    "mysql": {
        "host": "localhost",
        "user": "backup_user",
        "password": "backup_password"
    },
    "paths_to_backup": [
        "/etc/kamailio",
        "/etc/freeradius",
        "/etc/mysql",
        "/opt/monitoring"
    ]
}
```

## health-check.sh

### Opis
Kompleksowy skrypt bash do monitorowania stanu zdrowia wszystkich komponentów infrastruktury telecom-lab-ha3. Generuje raporty w formacie JSON i integruje się z systemami monitorowania.

### Funkcjonalności
- **Monitoring usług** - status Kamailio, FreeRADIUS, MySQL/Galera
- **Sprawdzanie portów** - weryfikacja nasłuchujących portów
- **Monitoring zasobów** - CPU, RAM, dysk, sieć
- **Testy połączeń** - connectivity między nodami
- **Alerty** - powiadomienia o problemach

### Składnia
```bash
./health-check.sh [OPCJE]
```

### Parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `-v, --verbose` | Szczegółowe logi | `./health-check.sh -v` |
| `-j, --json` | Wyjście w JSON | `./health-check.sh -j` |
| `-c, --config` | Plik konfiguracyjny | `./health-check.sh -c config.conf` |
| `-t, --timeout` | Timeout dla testów | `./health-check.sh -t 30` |
| `-a, --alert` | Wysyłaj alerty | `./health-check.sh -a` |

### Przykłady użycia

#### Podstawowe sprawdzenie
```bash
./health-check.sh
```

#### Sprawdzenie z alertami
```bash
./health-check.sh --verbose --alert --json > health-report.json
```

#### Monitoring ciągły
```bash
watch -n 30 './health-check.sh --json'
```

## maintenance.py

### Opis
Zaawansowany skrypt Python do zarządzania zadaniami konserwacyjnymi w środowisku telecom-lab-ha3. Automatyzuje rutynowe zadania i optymalizuje wydajność systemu.

### Funkcjonalności
- **Czyszczenie logów** - rotacja i archiwizacja
- **Optymalizacja bazy danych** - defragmentacja, aktualizacja statystyk
- **Aktualizacje systemu** - bezpieczne aktualizacje pakietów
- **Monitoring wydajności** - analiza i raportowanie
- **Konserwacja certyfikatów** - sprawdzanie ważności

### Składnia
```bash
python3 maintenance.py [OPCJE] [ZADANIE]
```

### Parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `--task` | Typ zadania konserwacyjnego | `--task cleanup` |
| `--schedule` | Harmonogram wykonania | `--schedule daily` |
| `--dry-run` | Symulacja bez zmian | `--dry-run` |
| `--force` | Wymusza wykonanie | `--force` |
| `--config` | Plik konfiguracyjny | `--config maintenance.conf` |

### Przykłady użycia

#### Czyszczenie systemu
```bash
python3 maintenance.py --task cleanup --dry-run
```

#### Optymalizacja bazy danych
```bash
python3 maintenance.py --task optimize-db --verbose
```

#### Pełna konserwacja
```bash
python3 maintenance.py --task full-maintenance --schedule weekly
```

## performance-monitor.sh

### Opis
Skrypt bash do monitorowania wydajności systemu w czasie rzeczywistym. Zbiera metryki wydajności, generuje raporty i może integrować się z systemami alertingu.

### Funkcjonalności
- **Monitoring CPU** - wykorzystanie, load average, procesy
- **Monitoring pamięci** - RAM, swap, cache
- **Monitoring dysku** - I/O, przestrzeń, IOPS
- **Monitoring sieci** - throughput, połączenia, błędy
- **Monitoring usług** - czas odpowiedzi, dostępność

### Składnia
```bash
./performance-monitor.sh [OPCJE]
```

### Parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `-i, --interval` | Interwał monitorowania | `-i 5` |
| `-d, --duration` | Czas monitorowania | `-d 3600` |
| `-o, --output` | Plik wyjściowy | `-o report.csv` |
| `-g, --graph` | Generuj wykresy | `-g` |
| `-a, --alert` | Progi alertów | `-a cpu:80,mem:90` |

### Przykłady użycia

#### Monitoring podstawowy
```bash
./performance-monitor.sh -i 10 -d 1800
```

#### Monitoring z alertami
```bash
./performance-monitor.sh -i 5 -a cpu:80,mem:90,disk:95
```

#### Generowanie raportu
```bash
./performance-monitor.sh -i 30 -d 86400 -o daily-report.csv -g
```

## service-manager.sh

### Opis
Uniwersalny skrypt bash do zarządzania wszystkimi usługami w środowisku telecom-lab-ha3. Zapewnia jednolity interfejs do kontroli usług SIP, RADIUS, bazy danych i monitoringu.

### Funkcjonalności
- **Kontrola usług** - start, stop, restart, status
- **Zarządzanie grupami** - operacje na zestawach usług
- **Sprawdzanie zależności** - kolejność startu usług
- **Monitoring stanu** - ciągłe sprawdzanie dostępności
- **Rollback** - przywracanie poprzedniego stanu

### Składnia
```bash
./service-manager.sh [AKCJA] [USŁUGA/GRUPA] [OPCJE]
```

### Parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `start` | Uruchom usługę | `start kamailio` |
| `stop` | Zatrzymaj usługę | `stop all` |
| `restart` | Zrestartuj usługę | `restart sip-stack` |
| `status` | Status usługi | `status database` |
| `enable` | Włącz autostart | `enable monitoring` |
| `disable` | Wyłącz autostart | `disable kamailio` |

### Przykłady użycia

#### Zarządzanie pojedynczą usługą
```bash
./service-manager.sh start kamailio
./service-manager.sh status freeradius
./service-manager.sh restart mariadb
```

#### Zarządzanie grupami usług
```bash
./service-manager.sh start sip-stack
./service-manager.sh restart database-cluster
./service-manager.sh stop all
```

#### Monitoring ciągły
```bash
./service-manager.sh monitor --interval 30 --alert
```

## sip_radius_diagnostics.py

### Opis
Zaawansowany skrypt Python do diagnostyki i testowania usług SIP (Kamalio) oraz RADIUS (FreeRADIUS). Wykonuje kompleksowe testy funkcjonalne, wydajnościowe i diagnostyczne.

### Funkcjonalności
- **Testy SIP** - rejestracja, wywołania, OPTIONS
- **Testy RADIUS** - autentykacja, accounting, dostępność
- **Analiza ruchu** - packet capture i analiza
- **Testy wydajności** - load testing, stress testing
- **Diagnostyka sieci** - connectivity, latency, throughput

### Składnia
```bash
python3 sip_radius_diagnostics.py [OPCJE] [TEST]
```

### Parametry

| Parametr | Opis | Przykład |
|----------|------|----------|
| `--test` | Typ testu | `--test sip-register` |
| `--target` | Adres docelowy | `--target 192.168.56.254` |
| `--port` | Port docelowy | `--port 5060` |
| `--username` | Nazwa użytkownika | `--username testuser` |
| `--password` | Hasło | `--password testpass` |
| `--duration` | Czas testu | `--duration 60` |
| `--verbose` | Szczegółowe logi | `--verbose` |

### Przykłady użycia

#### Test rejestracji SIP
```bash
python3 sip_radius_diagnostics.py --test sip-register --target 192.168.56.254 --username alice --password alice123
```

#### Test autentykacji RADIUS
```bash
python3 sip_radius_diagnostics.py --test radius-auth --target 192.168.56.254 --username testuser --password testpass
```

#### Kompleksowa diagnostyka
```bash
python3 sip_radius_diagnostics.py --test full-diagnostic --target 192.168.56.254 --verbose
```

#### Test wydajności
```bash
python3 sip_radius_diagnostics.py --test load-test --target 192.168.56.254 --duration 300 --concurrent 50
```

## 🚀 Wykorzystanie skryptów

### Integracja z monitoringiem
Wszystkie skrypty mogą być zintegrowane z systemem monitoringu Prometheus poprzez eksportowanie metryk w odpowiednim formacie.

### Automatyzacja przez cron
```bash
# Przykład wpisu w crontab
# Health check co 5 minut
*/5 * * * * /opt/scripts/health-check.sh --json >> /var/log/health-checks.log

# Backup codziennie o 2:00
0 2 * * * python3 /opt/scripts/backup_restore.py --backup full --encrypt

# Performance monitoring co godzinę
0 * * * * /opt/scripts/performance-monitor.sh -i 300 -d 3600 -o /var/log/perf-$(date +\%H).csv
```

### Integracja z GitOps
Skrypty mogą być aktualizowane automatycznie przez system GitOps i uruchamiane jako części pipeline'u CI/CD.
