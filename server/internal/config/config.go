package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	HTTPAddr     string
	DBDSN        string
	RedisEnabled bool
	RedisAddr    string
	RedisPass    string
	RedisDB      int
	AllowOrigins string
	PythonURL    string
	InternalToken string
}

func Load() Config {
	redisDB, _ := strconv.Atoi(getenv("REDIS_DB", "0"))
	return Config{
		HTTPAddr:      getenv("HTTP_ADDR", ":3001"),
		DBDSN:         getenv("DB_DSN", "root:030705@tcp(127.0.0.1:3306)/rjfinshed?charset=utf8mb4&parseTime=True&loc=Local"),
		RedisEnabled:  getenv("REDIS_ENABLED", "false") == "true",
		RedisAddr:     getenv("REDIS_ADDR", "127.0.0.1:6379"),
		RedisPass:     os.Getenv("REDIS_PASSWORD"),
		RedisDB:       redisDB,
		AllowOrigins:  getenv("ALLOW_ORIGINS", "http://127.0.0.1:5173"),
		PythonURL:     getenv("PYTHON_URL", "http://127.0.0.1:8000"),
		InternalToken: getenv("GO_INTERNAL_TOKEN", ""),
	}
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
