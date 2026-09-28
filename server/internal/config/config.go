package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	HTTPAddr      string
	DBDSN         string
	RedisEnabled  bool
	RedisAddr     string
	RedisPass     string
	RedisDB       int
	AllowOrigins  string
	PythonURL     string
	InternalToken string
	OCREnabled    bool
	OCRServiceURL string
	OCRTimeoutMS  int
}

func Load() Config {
	redisDB, _ := strconv.Atoi(getenv("REDIS_DB", "0"))
	ocrTimeoutMS, _ := strconv.Atoi(getenv("OCR_TIMEOUT_MS", "20000"))
	dsn := strings.TrimSpace(os.Getenv("DB_DSN"))
	if dsn == "" {
		host := getenv("DB_HOST", "")
		port := getenv("DB_PORT", "3306")
		user := getenv("DB_USER", "")
		password := os.Getenv("DB_PASSWORD")
		database := getenv("DB_NAME", "")
		if host != "" && user != "" && database != "" {
			dsn = fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?charset=utf8mb4&parseTime=True&loc=Local", user, password, host, port, database)
		}
	}
	return Config{
		HTTPAddr:      getenv("HTTP_ADDR", ":3001"),
		DBDSN:         dsn,
		RedisEnabled:  getenv("REDIS_ENABLED", "false") == "true",
		RedisAddr:     getenv("REDIS_ADDR", "127.0.0.1:6379"),
		RedisPass:     os.Getenv("REDIS_PASSWORD"),
		RedisDB:       redisDB,
		AllowOrigins:  getenv("ALLOW_ORIGINS", "http://127.0.0.1:5173"),
		PythonURL:     getenv("PYTHON_URL", "http://127.0.0.1:8000"),
		InternalToken: getenv("GO_INTERNAL_TOKEN", ""),
		OCREnabled:    getenv("OCR_ENABLED", "false") == "true",
		OCRServiceURL: getenv("OCR_SERVICE_URL", "http://127.0.0.1:8010/ocr"),
		OCRTimeoutMS:  ocrTimeoutMS,
	}
}

func (c Config) Validate() error {
	if strings.TrimSpace(c.DBDSN) == "" {
		return fmt.Errorf("database configuration is missing: set DB_DSN or DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, and DB_NAME")
	}
	return nil
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func (c Config) String() string {
	return fmt.Sprintf("http=%s redis_enabled=%t redis=%s", c.HTTPAddr, c.RedisEnabled, c.RedisAddr)
}
