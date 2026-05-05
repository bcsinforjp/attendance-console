# Installing attendance-doctor.timer

These files run [doctor.py](../doctor.py) every 5 hours via systemd.

## One-time install (run as root)

```bash
sudo cp /var/www/attendance_app/systemd/attendance-doctor.service /etc/systemd/system/
sudo cp /var/www/attendance_app/systemd/attendance-doctor.timer   /etc/systemd/system/

# Optional: edit the service to plug in an API key for auto-ingest of pending files
sudo nano /etc/systemd/system/attendance-doctor.service
# → uncomment + fill   Environment=ATTENDANCE_DOCTOR_KEY=app-XXXX

sudo systemctl daemon-reload
sudo systemctl enable --now attendance-doctor.timer
```

## Verify

```bash
systemctl list-timers attendance-doctor.timer
journalctl -u attendance-doctor.service -n 50
tail -n 100 /var/www/attendance_app/logs/internal_health_logs.log
```

## Run on demand (any time)

```bash
sudo systemctl start attendance-doctor.service
```

## Uninstall

```bash
sudo systemctl disable --now attendance-doctor.timer
sudo rm /etc/systemd/system/attendance-doctor.service /etc/systemd/system/attendance-doctor.timer
sudo systemctl daemon-reload
```
