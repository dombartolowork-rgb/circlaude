package main

// The pairing page: Orbit's own addition to the bridge.
//
// Upstream prints the QR into a terminal, once, and never redraws it when
// WhatsApp rotates the code. That is fine for a developer and useless for
// someone who has never opened a terminal. Orbit starts the bridge in the
// background and opens this page in their browser instead. It redraws itself
// every couple of seconds, so it always shows the current code, and turns into
// a "connected" message as soon as the phone has scanned it.
//
// Auth: the page shows a code that links a WhatsApp account, so it gets the
// same loopback Host check as the API. A browser cannot send a bearer header,
// so the token comes in the query string instead (`/pair?t=<token>`); Orbit
// reads the token file and builds that URL itself.

import (
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"html"
	"net/http"
	"sync"

	"go.mau.fi/whatsmeow"
	"rsc.io/qr"
)

type pairState struct {
	mu     sync.Mutex
	status string // starting, qr, paired, expired, outdated
	code   string
}

var pairing = &pairState{status: "starting"}

func (p *pairState) set(status, code string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.status, p.code = status, code
}

func (p *pairState) get() (string, string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.status, p.code
}

func pairHandler(client *whatsmeow.Client, token string, allowedHosts map[string]struct{}) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !hostAllowed(r.Host, allowedHosts) {
			http.Error(w, "Forbidden: host not allowed", http.StatusForbidden)
			return
		}
		got := r.URL.Query().Get("t")
		if len(got) != len(token) || subtle.ConstantTimeCompare([]byte(got), []byte(token)) != 1 {
			http.Error(w, "This link has expired. Go back to Claude and ask it to connect WhatsApp again.", http.StatusUnauthorized)
			return
		}

		status, code := pairing.get()
		if client.Store.ID != nil && client.IsConnected() {
			status = "connected"
		}

		var body string
		refresh := true
		switch status {
		case "qr":
			c, err := qr.Encode(code, qr.L)
			if err != nil {
				body = `<h1>Something went wrong</h1><p>The code could not be drawn. Go back to Claude and ask it to try again.</p>`
				break
			}
			c.Scale = 8
			img := base64.StdEncoding.EncodeToString(c.PNG())
			body = `<h1>Connect your WhatsApp</h1>
<ol>
<li>Open <b>WhatsApp</b> on your phone.</li>
<li>iPhone: tap <b>Settings</b>. Android: tap the <b>three dots</b>, top right.</li>
<li>Tap <b>Linked devices</b>, then <b>Link a device</b>.</li>
<li>Point your phone at this code.</li>
</ol>
<img alt="WhatsApp code" src="data:image/png;base64,` + img + `">
<p class="small">The code changes every 20 seconds or so. This page keeps up by itself, so just scan whatever is showing.</p>`
		case "paired", "connected":
			refresh = status == "paired"
			body = `<h1 class="ok">WhatsApp is connected</h1>
<p>You can close this page and go back to Claude.</p>
<p class="small">Your older messages will keep arriving for a few minutes. That happens in the background.</p>`
		case "expired":
			body = `<h1>The codes ran out</h1>
<p>WhatsApp only gives out a few codes before it stops. Go back to Claude and ask it to connect WhatsApp again.</p>`
		case "outdated":
			refresh = false
			body = `<h1>This needs an update</h1>
<p>WhatsApp has stopped accepting this version of Orbit's WhatsApp link. Let Dom know, and he will send an update.</p>`
		default:
			body = `<h1>Getting a code from WhatsApp...</h1><p class="small">This takes a few seconds.</p>`
		}

		meta := ""
		if refresh {
			meta = `<meta http-equiv="refresh" content="2">`
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		fmt.Fprintf(w, `<!doctype html><html><head><meta charset="utf-8">%s
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Orbit: connect WhatsApp</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f6f6f4;color:#1a1a1a;margin:0;display:flex;justify-content:center}
main{max-width:520px;margin:48px 16px;background:#fff;border-radius:16px;padding:32px 36px;box-shadow:0 2px 12px rgba(0,0,0,.06)}
h1{font-size:24px;margin:0 0 16px}
h1.ok{color:#1a7f37}
ol{padding-left:20px;line-height:1.7}
img{display:block;margin:20px auto;width:296px;height:296px;image-rendering:pixelated}
.small{color:#666;font-size:14px}
</style></head><body><main>%s<p class="small">%s</p></main></body></html>`,
			meta, body, html.EscapeString("Orbit Assistant, Circle Agency"))
	}
}
