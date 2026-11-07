package governance

import (
	"context"
	"errors"
	"io"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"time"
	"unicode/utf8"
)

const qualifiedCurl = "/usr/bin/curl"

func artifactCurlArguments(locator, output string, size int64) ([]string, error) {
	parsed, err := url.Parse(locator)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil {
		return nil, artifactAcquisitionError("curl transfer requires a credential-free HTTPS URL")
	}
	if size < 1 || size > genericArtifactLimit {
		return nil, artifactAcquisitionError("curl transfer size limit is outside the generic artifact budget")
	}
	return []string{"--disable", "--silent", "--show-error", "--fail", "--location", "--proto", "=https", "--proto-redir", "=https", "--http1.1", "--max-redirs", "5", "--retry", "2", "--retry-delay", "1", "--retry-max-time", "15", "--connect-timeout", "5", "--max-time", "30", "--max-filesize", strconv.FormatInt(size, 10), "--output", output, locator}, nil
}

func runArtifactCurl(ctx context.Context, locator, output string, size int64) (reason string, resultErr error) {
	args, err := artifactCurlArguments(locator, output, size)
	if err != nil {
		return "", err
	}
	defer func() {
		if reason != "" || resultErr != nil {
			if removeErr := os.Remove(output); removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
				resultErr = removeErr
			}
		}
	}()
	if failure, preflightErr := artifactCurlPreflight(ctx); preflightErr != nil || failure != "" {
		return failure, preflightErr
	}
	return artifactCurlTransfer(ctx, args, output, size)
}

func artifactCurlTransfer(ctx context.Context, args []string, output string, size int64) (string, error) {
	transfer, cancel := context.WithTimeout(ctx, 35*time.Second)
	defer cancel()
	command := exec.CommandContext(transfer, qualifiedCurl, args...) // #nosec G204 -- Fixed qualified executable and argv; no shell or candidate-supplied options.
	command.Env = artifactCurlEnvironment()
	command.Stdout = io.Discard
	command.Stderr = io.Discard
	err := command.Run()
	if cancelled := ctx.Err(); cancelled != nil {
		return "", cancelled
	}
	if transfer.Err() != nil {
		return "curl-wall-deadline", nil
	}
	if err == nil {
		info, inspectErr := os.Lstat(output)
		if inspectErr != nil || !info.Mode().IsRegular() || info.Size() > size {
			return "curl-size-limit-bypassed", nil
		}
		return "", nil
	}
	if exit, ok := errors.AsType[*exec.ExitError](err); ok {
		return artifactCurlExitReason(exit.ExitCode()), nil
	}
	return "curl-unavailable", nil
}
func artifactCurlEnvironment() []string { return []string{"LC_ALL=C", "LANG=C", "PATH=/usr/bin:/bin"} }
func artifactCurlExitReason(code int) string {
	switch code {
	case 63:
		return "curl-size-limit-enforced"
	case 35, 51, 58, 60, 77, 82, 83, 90, 91:
		return "curl-tls-rejected"
	case 28:
		return "curl-transfer-deadline"
	default:
		return "curl-transfer-failed"
	}
}

func artifactCurlPreflight(ctx context.Context) (string, error) {
	probe, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	stdout, stderr := &artifactProbeBuffer{}, &artifactProbeBuffer{}
	command := exec.CommandContext(probe, qualifiedCurl, "--version")
	command.Env = artifactCurlEnvironment()
	command.Stdout = stdout
	command.Stderr = stderr
	err := command.Run()
	if cancelled := ctx.Err(); cancelled != nil {
		return "", cancelled
	}
	if !utf8.Valid(stdout.data) || !utf8.Valid(stderr.data) {
		return "curl-version-inadequate", nil
	}
	if err != nil {
		return "curl-unavailable", nil
	}
	if stdout.total+stderr.total+1 > 8192 || !supportedCurlVersion(string(stdout.data)) {
		return "curl-version-inadequate", nil
	}
	return "", nil
}

type artifactProbeBuffer struct {
	data  []byte
	total int
}

func (b *artifactProbeBuffer) Write(data []byte) (int, error) {
	count := len(data)
	if len(b.data) < 8193 {
		b.data = append(b.data, data[:min(len(data), 8193-len(b.data))]...)
	}
	b.total = min(8193, b.total+min(len(data), 8193))
	return count, nil
}
func supportedCurlVersion(text string) bool {
	pattern, err := compileSchemaPattern(`(\d{1,10})[.](\d{1,10})[.](\d{1,10})`, true)
	if err != nil {
		return false
	}
	match := pattern.FindStringSubmatch(text)
	if match == nil {
		return false
	}
	values := [3]int64{}
	for i, token := range match[1:] {
		integer, valid := pythonIntegerText(token)
		if !valid {
			return false
		}
		value, err := strconv.ParseInt(integer, 10, 64)
		if err != nil {
			return false
		}
		values[i] = value
	}
	return values[0] > 8 || values[0] == 8 && values[1] >= 4
}
