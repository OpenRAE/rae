package governance

import (
	"context"
	"errors"
	"io"
	"math"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

func groundControlSetting(r *repository, name string) string {
	if value := strings.TrimFunc(os.Getenv(name), pythonWhitespace); value != "" {
		return value
	}
	data, err := r.read(".mcp.json")
	if err != nil {
		return ""
	}
	value, err := decodeJSON(data, 0, false)
	if err != nil {
		return ""
	}
	root, _ := value.(*mapping)
	servers, _ := root.get("mcpServers").(*mapping)
	server, _ := servers.get("ground-control").(*mapping)
	environment, _ := server.get("env").(*mapping)
	setting, _ := environment.get(name).(string)
	return strings.TrimFunc(setting, pythonWhitespace)
}

func (c *checker) httpRequirements(ctx context.Context, r *repository, policy *requirementPolicy, paths []string, uid string, scope *requirementScope, required bool) (Report, error) {
	base := groundControlSetting(r, "GC_BASE_URL")
	if base == "" {
		return unevaluatedGovernance("ground-control-config-missing", "GC_BASE_URL is not set; configure it in the environment or the repo-local .mcp.json ground-control server env", required), nil
	}
	authority := &httpAuthority{base: strings.TrimRight(base, "/"), token: groundControlSetting(r, "GROUND_CONTROL_API_TOKEN"), client: &http.Client{Timeout: requirementHTTPTimeout()}}
	findings, err := c.evaluateRequirements(ctx, r, policy, authority, paths, uid, scope)
	if unavailable, ok := errors.AsType[authorityError](err); ok {
		rule, message := "ground-control-unavailable", unavailable.message
		if unavailable.auth {
			rule, message = "ground-control-auth-required", "Ground Control requires authentication ("+message+")"
		}
		return unevaluatedGovernance(rule, message, required), nil
	}
	return finish(findings), err
}

const httpConnectionFailed = "connection failed"
const httpMalformedResponse = "malformed response"

type authorityError struct {
	message string
	auth    bool
}

func (e authorityError) Error() string { return e.message }

type httpAuthority struct {
	base, token string
	client      *http.Client
}

func requirementHTTPTimeout() time.Duration {
	seconds, err := strconv.ParseFloat(strings.TrimFunc(os.Getenv("GC_HTTP_TIMEOUT_SECONDS"), pythonWhitespace), 64)
	if err != nil || seconds <= 0 || math.IsNaN(seconds) || math.IsInf(seconds, 0) || seconds >= float64(math.MaxInt64)/float64(time.Second) {
		return 5 * time.Second
	}
	return max(time.Nanosecond, time.Duration(seconds*float64(time.Second)))
}

func (a *httpAuthority) request(ctx context.Context, path string) (any, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, a.base+path, nil)
	if err != nil {
		return nil, authorityError{message: httpConnectionFailed}
	}
	req.Header.Set("X-Actor", "repo-policy")
	if a.token != "" {
		req.Header.Set("Authorization", "Bearer "+a.token)
	}
	resp, err := a.client.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, authorityError{message: httpConnectionFailed}
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode >= http.StatusMultipleChoices {
		return nil, authorityError{message: "HTTP " + strconv.Itoa(resp.StatusCode), auth: resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden}
	}
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		if cancelled := ctx.Err(); cancelled != nil {
			return nil, cancelled
		}
		return nil, authorityError{message: httpConnectionFailed}
	}
	value, err := decodeJSON(data, 0, false)
	if err != nil {
		return nil, authorityError{message: httpMalformedResponse}
	}
	return value, nil
}

func (a *httpAuthority) get(ctx context.Context, project, uid string) (requirementFact, error) {
	value, err := a.request(ctx, "/api/v1/requirements/uid/"+uid+"?"+url.Values{"project": {project}}.Encode())
	if err != nil {
		return requirementFact{}, err
	}
	m, ok := value.(*mapping)
	status, valid := m.get("status").(string)
	if !ok || !valid || !m.has("id") || !m.has("uid") {
		return requirementFact{}, authorityError{message: httpMalformedResponse}
	}
	return requirementFact{id: m.get("id"), uid: m.get("uid"), status: status}, nil
}

func (a *httpAuthority) links(ctx context.Context, id any) ([]requirementLink, error) {
	value, err := a.request(ctx, "/api/v1/requirements/"+pythonStr(id)+"/traceability")
	if err != nil {
		return nil, err
	}
	items, ok := value.([]any)
	if !ok {
		return nil, authorityError{message: httpMalformedResponse}
	}
	links := make([]requirementLink, 0, len(items))
	for _, value := range items {
		link, err := httpRequirementLink(value)
		if err != nil {
			return nil, err
		}
		links = append(links, link)
	}
	return links, nil
}

func httpRequirementLink(value any) (requirementLink, error) {
	m, ok := value.(*mapping)
	if !ok {
		return requirementLink{}, authorityError{message: httpMalformedResponse}
	}
	values := []string{}
	for _, pair := range [][2]string{{"link_type", "linkType"}, {"artifact_type", "artifactType"}, {"artifact_identifier", "artifactIdentifier"}} {
		for _, key := range pair {
			if raw := m.get(key); raw != nil {
				if _, ok := raw.(string); !ok {
					return requirementLink{}, authorityError{message: httpMalformedResponse}
				}
			}
		}
		raw := m.get(pair[0])
		if raw == nil {
			raw = m.get(pair[1])
		}
		text, _ := raw.(string)
		values = append(values, text)
	}
	return requirementLink{kind: values[0], artifact: values[1], identifier: values[2]}, nil
}
