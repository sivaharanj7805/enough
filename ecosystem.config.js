const path = require('path');
const ROOT = path.resolve(__dirname);

module.exports = {
  apps: [
    {
      name: 'tended-backend',
      cwd: path.join(ROOT, 'backend'),
      script: 'python3',
      args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8000',
      interpreter: 'none',
      env_file: path.join(ROOT, 'backend', '.env'),
      autorestart: true,
      watch: false,
      max_memory_restart: '800M',
      error_file: path.join(ROOT, 'logs', 'backend-error.log'),
      out_file:   path.join(ROOT, 'logs', 'backend-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'tended-frontend',
      cwd: path.join(ROOT, 'frontend'),
      script: 'node_modules/.bin/next',
      args: 'start -p 3000',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '600M',
      error_file: path.join(ROOT, 'logs', 'frontend-error.log'),
      out_file:   path.join(ROOT, 'logs', 'frontend-out.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'tended-tunnel-be',
      script: 'cloudflared',
      args: 'tunnel --url http://localhost:8000',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      error_file: path.join(ROOT, 'logs', 'tunnel-be-error.log'),
      out_file:   path.join(ROOT, 'logs', 'tunnel-be-out.log'),
    },
    {
      name: 'tended-tunnel-fe',
      script: 'cloudflared',
      args: 'tunnel --url http://localhost:3000',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      error_file: path.join(ROOT, 'logs', 'tunnel-fe-error.log'),
      out_file:   path.join(ROOT, 'logs', 'tunnel-fe-out.log'),
    },
  ],
};
