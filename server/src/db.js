const mysql = require('mysql2/promise');

const pool = mysql.createPool({
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '3306'),
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '123321',
  database: process.env.DB_NAME || 'rjfinshed_v8_import',
  waitForConnections: true,
  connectionLimit: 10,
  timezone: '+08:00'
});

module.exports = pool;
