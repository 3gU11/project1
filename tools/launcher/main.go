package main

import (
	"bufio"
	"context"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const (
	exitOK          = 0
	exitPrecheck    = 1
	exitGoBuild     = 2
	exitGoHealth    = 3
	exitStartFailed = 4
)

type ports struct {
	goPort     string
	apiPort    string
	webPort    string
	mobilePort string
}

func main() {
	if code := run(); code != 0 {
		pauseOnExit()
		os.Exit(code)
	}
}

func run() int {
	dryRun := flag.Bool("dry-run", false, "print steps only")
	noMobile := flag.Bool("no-mobile", false, "skip frontend-mobile startup")
	portArg := flag.String("ports", "go=3001,api=8000,web=3000,mobile=5174", "override ports")
	pythonPath := flag.String("python", `C:\Users\zc123\python-sdk\python3.13.2\python.exe`, "python executable")
	flag.Parse()

	p, err := parsePorts(*portArg)
	if err != nil {
		errLog("invalid --ports: %v", err)
		return exitPrecheck
	}

	root, err := os.Getwd()
	if err != nil {
		errLog("failed to get cwd: %v", err)
		return exitPrecheck
	}
	serverDir := filepath.Join(root, "server")
	frontendDir := filepath.Join(root, "frontend")
	mobileDir := filepath.Join(root, "frontend-mobile")
	goExe := filepath.Join(serverDir, "smart-scheduling-server-go.exe")

	log("========================================")
	log("V7 Fullstack Launcher (.exe)")
	log("ROOT: %s", root)
	log("========================================")

	if _, err := os.Stat(filepath.Join(serverDir, "cmd", "main.go")); err != nil {
		errLog("missing %s", filepath.Join(serverDir, "cmd", "main.go"))
		return exitPrecheck
	}
	if _, err := os.Stat(filepath.Join(frontendDir, "package.json")); err != nil {
		errLog("missing %s", filepath.Join(frontendDir, "package.json"))
		return exitPrecheck
	}
	goBin := "go"
	if !*dryRun {
		if resolved, err := resolveGoBin(root); err != nil {
			errLog("go not found in PATH and common locations: %v", err)
			return exitPrecheck
		} else {
			goBin = resolved
			log("Using Go: %s", goBin)
		}
	}

	gocache := filepath.Join(serverDir, ".gocache-build")
	gomodcache := filepath.Join(serverDir, ".gomodcache-build")
	if !*dryRun {
		_ = os.MkdirAll(gocache, 0o755)
		_ = os.MkdirAll(gomodcache, 0o755)
	}

	log("[1/4] Building Go sandbox binary...")
	if *dryRun {
		log("[DRY-RUN] go build -o %q .\\cmd\\main.go", goExe)
	} else {
		env := map[string]string{"GOCACHE": gocache, "GOMODCACHE": gomodcache}
		_, err := runAndWait(goBin, []string{"build", "-o", goExe, ".\\cmd\\main.go"}, serverDir, env)
		if err != nil {
			errLog("Go build failed: %v", err)
			return exitGoBuild
		}
	}

	log("[2/4] Starting Go sandbox on %s...", p.goPort)
	if *dryRun {
		log("[DRY-RUN] start Go process")
	} else {
		if err := startScriptWindow("V7 Go Sandbox", root, []string{
			fmt.Sprintf("cd /d \"%s\"", serverDir),
			fmt.Sprintf("set HTTP_ADDR=:%s", p.goPort),
			"smart-scheduling-server-go.exe",
		}); err != nil {
			errLog("start Go process failed: %v", err)
			return exitStartFailed
		}
	}

	log("Waiting for Go health...")
	if *dryRun {
		log("[DRY-RUN] skip health check")
	} else {
		url := fmt.Sprintf("http://127.0.0.1:%s/api/health", p.goPort)
		if err := waitHealth(url, 30*time.Second); err != nil {
			errLog("Go health check failed: %v", err)
			return exitGoHealth
		}
	}

	log("[3/4] Starting FastAPI on %s...", p.apiPort)
	if *dryRun {
		log("[DRY-RUN] start FastAPI process")
	} else {
		if err := startScriptWindow("V7 FastAPI", root, []string{
			fmt.Sprintf("cd /d \"%s\"", root),
			fmt.Sprintf("set GO_SANDBOX_URL=http://127.0.0.1:%s", p.goPort),
			fmt.Sprintf("\"%s\" -m uvicorn api.main:app --host 0.0.0.0 --port %s", *pythonPath, p.apiPort),
		}); err != nil {
			errLog("start FastAPI failed: %v", err)
			return exitStartFailed
		}
	}

	log("[4/4] Starting V7 frontend on %s...", p.webPort)
	if *dryRun {
		log("[DRY-RUN] start frontend process")
	} else {
		if err := startScriptWindow("V7 Frontend", root, []string{
			fmt.Sprintf("cd /d \"%s\"", frontendDir),
			"set VITE_API_BASE_URL=/api/v1",
			fmt.Sprintf("set VITE_PROXY_TARGET=http://127.0.0.1:%s", p.apiPort),
			fmt.Sprintf("npm run dev -- --host 0.0.0.0 --port %s", p.webPort),
		}); err != nil {
			errLog("start frontend failed: %v", err)
			return exitStartFailed
		}
	}

	if *noMobile {
		log("[Optional] Skip mobile frontend: --no-mobile")
	} else if _, err := os.Stat(filepath.Join(mobileDir, "package.json")); err == nil {
		log("[Optional] Starting mobile frontend on %s...", p.mobilePort)
		if *dryRun {
			log("[DRY-RUN] start mobile frontend process")
		} else {
			if err := startScriptWindow("V7 Mobile Frontend", root, []string{
				fmt.Sprintf("cd /d \"%s\"", mobileDir),
				fmt.Sprintf("npm run dev -- --host 0.0.0.0 --port %s", p.mobilePort),
			}); err != nil {
				errLog("start mobile frontend failed: %v", err)
				return exitStartFailed
			}
		}
	} else {
		log("[Optional] Skip mobile frontend: package.json not found")
	}

	log(".")
	log("Started. Check these windows:")
	log("- V7 Go Sandbox")
	log("- V7 FastAPI")
	log("- V7 Frontend")
	log(".")
	log("URLs:")
	log("- Go health: http://127.0.0.1:%s/api/health", p.goPort)
	log("- API docs : http://127.0.0.1:%s/docs", p.apiPort)
	log("- Frontend : http://127.0.0.1:%s", p.webPort)
	log("- Mobile   : http://127.0.0.1:%s", p.mobilePort)
	if *dryRun {
		log("[DRY-RUN] completed.")
	}

	return exitOK
}

func runAndWait(bin string, args []string, dir string, env map[string]string) (int, error) {
	cmdline := append([]string{bin}, args...)
	proc, err := os.StartProcess(bin, cmdline, &os.ProcAttr{
		Dir:   dir,
		Env:   mergeEnv(env),
		Files: []*os.File{os.Stdin, os.Stdout, os.Stderr},
	})
	if err != nil {
		return -1, err
	}
	state, err := proc.Wait()
	if err != nil {
		return -1, err
	}
	if code := state.ExitCode(); code != 0 {
		return code, fmt.Errorf("exit code %d", code)
	}
	return 0, nil
}

func resolveGoBin(root string) (string, error) {
	candidates := []string{
		`C:\Program Files\Go\bin\go.exe`,
		filepath.Join(root, "server", "go", "bin", "go.exe"),
	}
	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			return p, nil
		}
	}
	return "", fmt.Errorf("no go executable found")
}

func pauseOnExit() {
	fmt.Println("Press Enter to exit...")
	_, _ = bufio.NewReader(os.Stdin).ReadString('\n')
}

func mergeEnv(extra map[string]string) []string {
	base := os.Environ()
	if len(extra) == 0 {
		return base
	}
	out := make([]string, 0, len(base)+len(extra))
	seen := map[string]bool{}
	for _, kv := range base {
		eq := strings.Index(kv, "=")
		if eq <= 0 {
			out = append(out, kv)
			continue
		}
		k := kv[:eq]
		if v, ok := extra[k]; ok {
			out = append(out, k+"="+v)
			seen[k] = true
		} else {
			out = append(out, kv)
		}
	}
	for k, v := range extra {
		if !seen[k] {
			out = append(out, k+"="+v)
		}
	}
	return out
}

func parsePorts(s string) (ports, error) {
	p := ports{goPort: "3001", apiPort: "8000", webPort: "3000", mobilePort: "5174"}
	for _, part := range strings.Split(s, ",") {
		kv := strings.SplitN(strings.TrimSpace(part), "=", 2)
		if len(kv) != 2 {
			return p, fmt.Errorf("bad pair: %q", part)
		}
		key := strings.TrimSpace(strings.ToLower(kv[0]))
		val := strings.TrimSpace(kv[1])
		if val == "" {
			return p, fmt.Errorf("empty port for %s", key)
		}
		switch key {
		case "go":
			p.goPort = val
		case "api":
			p.apiPort = val
		case "web":
			p.webPort = val
		case "mobile":
			p.mobilePort = val
		default:
			return p, fmt.Errorf("unknown key: %s", key)
		}
	}
	return p, nil
}

func startCmdWindow(title, command, dir string) error {
	c := cmdExe()
	_ = title
	_, err := runAndWait(c, []string{"/c", "start", "", c, "/k", command}, dir, nil)
	return err
}

func startScriptWindow(title, dir string, lines []string) error {
	scriptPath := filepath.Join(os.TempDir(), "v7-launcher-"+sanitizeTitle(title)+"-"+strconv.FormatInt(time.Now().UnixNano(), 10)+".cmd")
	content := "@echo off\r\nchcp 65001 >nul\r\n" + strings.Join(lines, "\r\n") + "\r\n"
	if err := os.WriteFile(scriptPath, []byte(content), 0o644); err != nil {
		return err
	}
	return startCmdWindow(title, "call "+quoteForCmd(scriptPath), dir)
}

func sanitizeTitle(s string) string {
	r := strings.NewReplacer(" ", "-", "\\", "-", "/", "-", ":", "-", "\"", "-", "'", "-")
	return r.Replace(strings.ToLower(strings.TrimSpace(s)))
}

func quoteForCmd(s string) string {
	return `"` + strings.ReplaceAll(s, `"`, `""`) + `"`
}

func cmdExe() string {
	if c := strings.TrimSpace(os.Getenv("ComSpec")); c != "" {
		return c
	}
	return `C:\Windows\System32\cmd.exe`
}

func waitHealth(url string, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	client := &http.Client{Timeout: 2 * time.Second}
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		resp, err := client.Do(req)
		if err == nil {
			_ = resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		select {
		case <-ctx.Done():
			if errors.Is(ctx.Err(), context.DeadlineExceeded) {
				return fmt.Errorf("timeout waiting for %s", url)
			}
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func log(format string, args ...interface{}) {
	fmt.Printf(format+"\n", args...)
}

func errLog(format string, args ...interface{}) {
	fmt.Printf("[ERROR] "+format+"\n", args...)
}
