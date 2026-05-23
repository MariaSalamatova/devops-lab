#!/bin/bash
if [ "$EUID" -ne 0 ]; then
    echo "Start script with sudo."
    exit 1
fi
set -e
apt-get update
apt-get install -y mariadb-server nginx python3-pip python3-venv python3-full curl sudo
if ! id "student" &>/dev/null; then
    useradd -m -s /bin/bash student || true
    echo "student ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/student
fi
if ! id "teacher" &>/dev/null; then
    useradd -m -s /bin/bash teacher || true
    echo "teacher:12345678" | chpasswd
    passwd -e teacher
    echo "teacher ALL=(ALL) ALL" > /etc/sudoers.d/teacher
fi
if ! id "app" &>/dev/null; then
    useradd -r -s /bin/false app || true
fi
if ! id "operator" &>/dev/null; then
    useradd -m -g operator -s /bin/bash operator 2>/dev/null || useradd -m -s /bin/bash operator || true
    echo "operator:12345678" | chpasswd
    passwd -e operator
    cat << 'EOF' > /etc/sudoers.d/operator
operator ALL=(ALL) NOPASSWD: /usr/bin/systemctl start mywebapp, /usr/bin/systemctl stop mywebapp, /usr/bin/systemctl restart mywebapp, /usr/bin/systemctl status mywebapp, /usr/bin/systemctl reload nginx
EOF
fi
systemctl start mariadb
systemctl enable mariadb
mysql -e "CREATE DATABASE IF NOT EXISTS mywebapp_db;"
mysql -e "CREATE USER IF NOT EXISTS 'webapp_user'@'127.0.0.1' IDENTIFIED BY 'secure_password';"
mysql -e "GRANT ALL PRIVILEGES ON mywebapp_db.* TO 'webapp_user'@'127.0.0.1';"
mysql -e "FLUSH PRIVILEGES;"
mkdir -p /opt/mywebapp
cp mywebapp.py /opt/mywebapp/mywebapp.py
python3 -m venv /opt/mywebapp/venv
/opt/mywebapp/venv/bin/pip install --upgrade pip
/opt/mywebapp/venv/bin/pip install flask mysql-connector-python werkzeug
chown -R app:app /opt/mywebapp
cat << 'EOF' > /etc/systemd/system/mywebapp.socket
[Unit]
Description=Socket for MyWebApp
[Socket]
ListenStream=127.0.0.1:5000
NoDelay=true
[Install]
WantedBy=sockets.target
EOF
cat << 'EOF' > /etc/systemd/system/mywebapp.service
[Unit]
Description=MyWebApp Task Tracker Service
Requires=mywebapp.socket mariadb.service
After=network.target mariadb.service
[Service]
Type=simple
User=app
Group=app
WorkingDirectory=/opt/mywebapp
# Fix 4: багаторядкові Environment та ExecStart склеєно в один рядок кожен
Environment=APP_HOST=127.0.0.1 APP_PORT=5000 DB_HOST=127.0.0.1 DB_USER=webapp_user DB_PASSWORD=secure_password DB_NAME=mywebapp_db
ExecStartPre=/opt/mywebapp/venv/bin/python /opt/mywebapp/mywebapp.py --migrate
ExecStart=/opt/mywebapp/venv/bin/python /opt/mywebapp/mywebapp.py --host 127.0.0.1 --port 5000 --socket_fd 3
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now mywebapp.socket
cat << 'EOF' > /etc/nginx/sites-available/mywebapp
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    access_log /var/log/nginx/mywebapp_access.log;
    location = / {
        proxy_pass http://127.0.0.1:5000/;
        proxy_set_header Host $host;
    }
    location /tasks {
        proxy_pass http://127.0.0.1:5000/tasks;
        proxy_set_header Host $host;
    }
    location / {
        return 403 "Access Denied. Internal endpoints are protected.";
    }
}
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/mywebapp /etc/nginx/sites-enabled/
systemctl restart nginx
systemctl enable nginx
echo "21" > /home/student/gradebook
chown student:student /home/student/gradebook
TARGET_USER=${SUDO_USER:-ubuntu}
if [ "$TARGET_USER" != "root" ] && [ "$TARGET_USER" != "student" ]; then
    usermod -L -s /usr/sbin/nologin "$TARGET_USER" 2>/dev/null || true
fi
echo "Successfully finished"