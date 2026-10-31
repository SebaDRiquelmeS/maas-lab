"""Executed as root inside the controller; URL is injected by lab.py."""
import json
import os
from pathlib import Path
import secrets
import subprocess

os.umask(0o077)
def run(args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)
p = Path('/root/lab-credentials.json')
if not p.exists():
    p.write_text(json.dumps({'admin_user': 'admin', 'admin_password': secrets.token_urlsafe(24),
                             'db_password': secrets.token_hex(24), 'url': URL}, indent=2))
c = json.loads(p.read_text())
# Existing database and role are inspected, never dropped or overwritten.
result = run(['postgresql.psql', '-U', 'postgres', '-h', '/tmp', '-Atc',
              "SELECT 1 FROM pg_roles WHERE rolname='maas'"], stdout=subprocess.PIPE)
if result.stdout.strip() != '1':
    run(['postgresql.psql', '-U', 'postgres', '-h', '/tmp', '-v', 'ON_ERROR_STOP=1'],
        input=f"CREATE USER maas WITH PASSWORD '{c['db_password']}';\n")
result = run(['postgresql.psql', '-U', 'postgres', '-h', '/tmp', '-Atc',
              "SELECT 1 FROM pg_database WHERE datname='maas'"], stdout=subprocess.PIPE)
if result.stdout.strip() != '1':
    run(['postgresql.createdb', '-U', 'postgres', '-h', '/tmp', '-O', 'maas', 'maas'])
mode = Path('/var/snap/maas/common/snap_mode')
if not mode.exists() or mode.read_text().strip() not in ('region+rack', 'region'):
    run(['maas', 'init', 'region+rack', '--maas-url', URL, '--num-workers', '2',
         '--database-uri', f"postgres://maas:{c['db_password']}@localhost/maas"])
# The snap creates its Django auth tables; query before creating the administrator.
result = run(['postgresql.psql', '-U', 'postgres', '-h', '/tmp', '-d', 'maas', '-Atc',
              "SELECT 1 FROM auth_user WHERE username='admin'"], stdout=subprocess.PIPE)
if result.stdout.strip() != '1':
    run(['maas', 'createadmin', '--username', 'admin', '--password', c['admin_password'], '--email', 'admin@localhost'])
key = subprocess.check_output(['maas', 'apikey', '--username', 'admin'], text=True).strip().splitlines()[0]
run(['maas', 'login', 'lab', URL + 'api/2.0/', key], stdout=subprocess.DEVNULL)
print('Administrador y perfil API preparados. Secretos en /root/lab-credentials.json.')
