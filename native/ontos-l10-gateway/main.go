// ONTOS L10 finite native gateway — an independent Go/std library process.
// This is a deterministic substitute for selected process/transport properties.
// It is NOT Zenoh, Rust, WASI, a cryptographic trust anchor or real FPGA control.
package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

type wire struct {
	V        string `json:"v"`
	C        string `json:"c"`
	T        string `json:"t"`
	N        string `json:"n"`
	S        uint32 `json:"s"`
	Issued   uint64 `json:"issued"`
	Expires  uint64 `json:"expires"`
	Payload  string `json:"payload"`
	Checksum string `json:"checksum"`
}

type proofToken struct {
	Schema          string `json:"schema"`
	Shell           string `json:"shell_sha256"`
	Tenant          string `json:"tenant"`
	Proposal        string `json:"proposal_sha256"`
	Equivalence     string `json:"equivalence_sha256"`
	Noninterference string `json:"noninterference_sha256"`
	Schedules       string `json:"schedules_sha256"`
	HarmBound       string `json:"harm_bound_sha256"`
	HarmUpperPPM    int    `json:"harm_upper_ppm"`
	Policy          string `json:"policy_version"`
	Epoch           int    `json:"epoch"`
	Expires         int    `json:"expires_tick"`
	Signature       string `json:"signature_ed25519_hex"`
}

type body struct {
	Kind        string      `json:"kind"`
	Cap         *string     `json:"cap"`
	Alarm       bool        `json:"alarm"`
	Attestation *proofToken `json:"attestation,omitempty"`
}

type gateway struct {
	mu         sync.Mutex
	tenant     string
	shell      string
	trusted    ed25519.PublicKey
	signer     ed25519.PrivateKey
	next       uint32
	last       uint64
	nonces     map[string]bool
	capMask    uint8
	phase      string
	epoch      int
	stateFile  string
	anchorHead string
	poisoned   bool
}

var ident = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)
var hex64 = regexp.MustCompile(`^[0-9a-f]{64}$`)

func jsonMap(fields map[string]any) ([]byte, error) { return json.Marshal(fields) }
func coreFields(w wire) map[string]any {
	return map[string]any{"v": w.V, "c": w.C, "t": w.T, "n": w.N, "s": w.S,
		"issued": w.Issued, "expires": w.Expires, "payload": w.Payload}
}
func parse(raw []byte) (wire, []byte, error) {
	var w wire
	if len(raw) == 0 || len(raw) > 8192 {
		return w, nil, errors.New("wire budget")
	}
	if err := json.Unmarshal(raw, &w); err != nil {
		return w, nil, err
	}
	if w.V != "ontos-ipc-v1" || len(w.C) != 1 || !strings.Contains("ABCDE", w.C) ||
		!ident.MatchString(w.T) || !ident.MatchString(w.N) ||
		w.Expires < w.Issued || !hex64.MatchString(w.Checksum) {
		return w, nil, errors.New("wire field")
	}
	payload, err := base64.StdEncoding.Strict().DecodeString(w.Payload)
	if err != nil || len(payload) > 4096 {
		return w, nil, errors.New("payload")
	}
	core, err := jsonMap(coreFields(w))
	if err != nil {
		return w, nil, err
	}
	digest := sha256.Sum256(core)
	if hex.EncodeToString(digest[:]) != w.Checksum {
		return w, nil, errors.New("checksum")
	}
	full := coreFields(w)
	full["checksum"] = w.Checksum
	canonical, err := jsonMap(full)
	if err != nil || !bytes.Equal(canonical, raw) {
		return w, nil, errors.New("not canonical")
	}
	return w, payload, nil
}
func canonicalBody(payload []byte) (body, error) {
	var b body
	if len(payload) == 0 || len(payload) > 4096 {
		return b, errors.New("payload budget")
	}
	d := json.NewDecoder(bytes.NewReader(payload))
	d.DisallowUnknownFields()
	if err := d.Decode(&b); err != nil {
		return b, err
	}
	if extra := d.Decode(&struct{}{}); extra != io.EOF {
		return b, errors.New("trailing json")
	}
	if b.Kind == "" {
		return b, errors.New("no action")
	}
	// The incoming message must be byte-canonical, including explicit null cap.
	root := map[string]any{"kind": b.Kind, "cap": b.Cap, "alarm": b.Alarm}
	if b.Attestation != nil {
		token := b.Attestation
		root["attestation"] = map[string]any{
			"schema": token.Schema, "shell_sha256": token.Shell, "tenant": token.Tenant,
			"proposal_sha256": token.Proposal, "equivalence_sha256": token.Equivalence,
			"noninterference_sha256": token.Noninterference, "schedules_sha256": token.Schedules,
			"harm_bound_sha256": token.HarmBound, "harm_upper_ppm": token.HarmUpperPPM,
			"policy_version": token.Policy, "epoch": token.Epoch, "expires_tick": token.Expires,
			"signature_ed25519_hex": token.Signature}
	}
	norm, err := jsonMap(root)
	if err != nil || !bytes.Equal(norm, payload) {
		return b, errors.New("noncanonical body")
	}
	return b, nil
}
func (g *gateway) checkAttestation(token *proofToken, at uint64) bool {
	if token == nil || token.Schema != "ontos-l10-release-v2" || token.Shell != g.shell ||
		token.Tenant != g.tenant || token.Epoch != g.epoch || token.Expires < 0 || at > uint64(token.Expires) ||
		!hex64.MatchString(token.Equivalence) || !hex64.MatchString(token.Proposal) ||
		!hex64.MatchString(token.Noninterference) || !hex64.MatchString(token.Schedules) ||
		!hex64.MatchString(token.HarmBound) || token.HarmUpperPPM < 0 || token.HarmUpperPPM > 50000 ||
		token.Policy != "ontos-l10-policy-4-verifiers-v1" {
		return false
	}
	sig, err := hex.DecodeString(token.Signature)
	if err != nil || len(sig) != ed25519.SignatureSize {
		return false
	}
	root := map[string]any{"schema": token.Schema, "shell_sha256": token.Shell,
		"tenant": token.Tenant, "proposal_sha256": token.Proposal,
		"equivalence_sha256": token.Equivalence, "noninterference_sha256": token.Noninterference,
		"schedules_sha256": token.Schedules, "harm_bound_sha256": token.HarmBound,
		"harm_upper_ppm": token.HarmUpperPPM, "policy_version": token.Policy,
		"epoch": token.Epoch, "expires_tick": token.Expires}
	data, err := jsonMap(root)
	return err == nil && ed25519.Verify(g.trusted, data, sig)
}

type checkpoint struct {
	Tenant    string   `json:"tenant"`
	Shell     string   `json:"shell"`
	Next      uint32   `json:"next"`
	Last      uint64   `json:"last"`
	CapMask   uint8    `json:"cap_mask"`
	Phase     string   `json:"phase"`
	Epoch     int      `json:"epoch"`
	Nonces    []string `json:"nonces"`
	Signature string   `json:"signature_ed25519_hex"`
}

func checkpointFields(c checkpoint) map[string]any {
	return map[string]any{"tenant": c.Tenant, "shell": c.Shell, "next": c.Next,
		"last": c.Last, "cap_mask": c.CapMask, "phase": c.Phase, "epoch": c.Epoch, "nonces": c.Nonces}
}
func (g *gateway) snapshot() checkpoint {
	names := make([]string, 0, len(g.nonces))
	for n := range g.nonces {
		names = append(names, n)
	}
	sort.Strings(names)
	return checkpoint{Tenant: g.tenant, Shell: g.shell, Next: g.next, Last: g.last,
		CapMask: g.capMask, Phase: g.phase, Epoch: g.epoch, Nonces: names}
}
func (g *gateway) restore(c checkpoint) {
	g.next = c.Next
	g.last = c.Last
	g.capMask = c.CapMask
	g.phase = c.Phase
	g.epoch = c.Epoch
	g.nonces = make(map[string]bool, len(c.Nonces))
	for _, n := range c.Nonces {
		g.nonces[n] = true
	}
}
func validateCheckpoint(c checkpoint, tenant, shell string) bool {
	if c.Tenant != tenant || c.Shell != shell || c.Next > 1024 || c.CapMask > 7 ||
		c.Epoch != 1 || len(c.Nonces) != int(c.Next) {
		return false
	}
	if c.Phase != "IDLE" && c.Phase != "OBSERVED" && c.Phase != "ASSESSED" &&
		c.Phase != "MODEL_APPROVED" && c.Phase != "LOCKDOWN" {
		return false
	}
	if c.Phase == "MODEL_APPROVED" && c.CapMask != 2 {
		return false
	}
	if c.Phase == "LOCKDOWN" && c.CapMask != 0 {
		return false
	}
	seen := map[string]bool{}
	for _, n := range c.Nonces {
		if !ident.MatchString(n) || seen[n] {
			return false
		}
		seen[n] = true
	}
	return true
}

type stateAnchor struct {
	Counter     uint32 `json:"counter"`
	StateSHA256 string `json:"state_sha256"`
	Prev        string `json:"previous_anchor_sha256"`
	Signature   string `json:"signature_ed25519_hex"`
}

func anchorFields(a stateAnchor) map[string]any {
	return map[string]any{"counter": a.Counter, "state_sha256": a.StateSHA256,
		"previous_anchor_sha256": a.Prev}
}
func regularPrivateFile(path string) ([]byte, error) {
	stat, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !stat.Mode().IsRegular() || stat.Mode().Perm() != 0600 || stat.Size() > 100000 {
		return nil, errors.New("unsafe private file mode/size")
	}
	return os.ReadFile(path)
}
func atomicWrite(path string, data []byte) error {
	parent := filepath.Dir(path)
	fd, err := os.CreateTemp(parent, ".ontos-atomic-*")
	if err != nil {
		return err
	}
	temp := fd.Name()
	defer os.Remove(temp)
	if err = fd.Chmod(0600); err != nil {
		fd.Close()
		return err
	}
	if _, err = fd.Write(data); err != nil {
		fd.Close()
		return err
	}
	if err = fd.Sync(); err != nil {
		fd.Close()
		return err
	}
	if err = fd.Close(); err != nil {
		return err
	}
	if err = os.Rename(temp, path); err != nil {
		return err
	}
	directory, err := os.Open(parent)
	if err != nil {
		return err
	}
	defer directory.Close()
	return directory.Sync()
}
func (g *gateway) persist() error {
	if g.stateFile == "" {
		return errors.New("missing persistent state path")
	}
	c := g.snapshot()
	if !validateCheckpoint(c, g.tenant, g.shell) {
		return errors.New("invalid state checkpoint")
	}
	canonical, _ := jsonMap(checkpointFields(c))
	c.Signature = hex.EncodeToString(ed25519.Sign(g.signer, canonical))
	body, _ := jsonMap(map[string]any{"tenant": c.Tenant, "shell": c.Shell, "next": c.Next,
		"last": c.Last, "cap_mask": c.CapMask, "phase": c.Phase, "epoch": c.Epoch,
		"nonces": c.Nonces, "signature_ed25519_hex": c.Signature})
	stateHash := sha256.Sum256(body)
	previous := g.anchorHead
	if previous == "" {
		previous = strings.Repeat("0", 64)
	}
	anchor := stateAnchor{Counter: c.Next, StateSHA256: hex.EncodeToString(stateHash[:]), Prev: previous}
	unsigned, _ := jsonMap(anchorFields(anchor))
	anchor.Signature = hex.EncodeToString(ed25519.Sign(g.signer, unsigned))
	anchored := anchorFields(anchor)
	anchored["signature_ed25519_hex"] = anchor.Signature
	anchorRaw, _ := jsonMap(anchored)
	newHead := sha256.Sum256(anchorRaw)
	// First update the separate signed witness; any interrupted pair remains
	// unbootable (fail-closed), not silently rolled back to older rights.
	if err := atomicWrite(g.stateFile+".anchor", anchorRaw); err != nil {
		return err
	}
	if err := atomicWrite(g.stateFile, body); err != nil {
		return err
	}
	g.anchorHead = hex.EncodeToString(newHead[:])
	return nil
}
func (g *gateway) loadState() error {
	raw, err := regularPrivateFile(g.stateFile)
	if err != nil {
		return err
	}
	anchorRaw, err := regularPrivateFile(g.stateFile + ".anchor")
	if err != nil {
		return err
	}
	var anchor stateAnchor
	if err = json.Unmarshal(anchorRaw, &anchor); err != nil {
		return err
	}
	anchorBody := anchorFields(anchor)
	anchorCanon, _ := jsonMap(anchorBody)
	anchorSigned := anchorFields(anchor)
	anchorSigned["signature_ed25519_hex"] = anchor.Signature
	anchorWire, _ := jsonMap(anchorSigned)
	anchorSig, err := hex.DecodeString(anchor.Signature)
	if err != nil || len(anchorSig) != ed25519.SignatureSize ||
		!ed25519.Verify(g.signer.Public().(ed25519.PublicKey), anchorCanon, anchorSig) ||
		!bytes.Equal(anchorWire, anchorRaw) {
		return errors.New("state anchor invalid")
	}
	h := sha256.Sum256(raw)
	if anchor.StateSHA256 != hex.EncodeToString(h[:]) {
		return errors.New("checkpoint rollback/mismatch detected")
	}
	hAnchor := sha256.Sum256(anchorRaw)
	var c checkpoint
	if err = json.Unmarshal(raw, &c); err != nil {
		return err
	}
	if !validateCheckpoint(c, g.tenant, g.shell) {
		return errors.New("invalid state contents")
	}
	canonical, _ := jsonMap(checkpointFields(c))
	signature, err := hex.DecodeString(c.Signature)
	if err != nil || len(signature) != ed25519.SignatureSize ||
		!ed25519.Verify(g.signer.Public().(ed25519.PublicKey), canonical, signature) {
		return errors.New("checkpoint signature invalid")
	}
	all := checkpointFields(c)
	all["signature_ed25519_hex"] = c.Signature
	encoded, _ := jsonMap(all)
	if !bytes.Equal(encoded, raw) {
		return errors.New("noncanonical signed state")
	}
	if anchor.Counter != c.Next {
		return errors.New("checkpoint counter mismatch")
	}
	g.restore(c)
	g.anchorHead = hex.EncodeToString(hAnchor[:])
	return nil
}
func (g *gateway) withPersistence(commit func()) bool {
	before := g.snapshot()
	commit()
	if err := g.persist(); err != nil {
		g.restore(before)
		g.capMask = 0
		g.phase = "LOCKDOWN"
		g.poisoned = true
		return false
	}
	return true
}
func (g *gateway) signed(status string) map[string]any {
	msg := map[string]any{"status": status, "phase": g.phase, "sequence": g.next,
		"cap_mask": int(g.capMask), "operational_capabilities_granted": false,
		"native_go_process_verified": true, "rust_zenoh_wasi_verified": false,
		"physical_fpga_reconfigured": false}
	raw, _ := jsonMap(msg)
	msg["signature_ed25519_hex"] = hex.EncodeToString(ed25519.Sign(g.signer, raw))
	return msg
}
func (g *gateway) signedDFX(status string, w wire, t *proofToken) map[string]any {
	base := g.signed(status)
	delete(base, "signature_ed25519_hex")
	base["tenant"] = g.tenant
	base["shell_sha256"] = g.shell
	base["request_nonce"] = w.N
	base["request_sequence"] = w.S
	base["proposal_sha256"] = t.Proposal
	base["equivalence_sha256"] = t.Equivalence
	base["noninterference_sha256"] = t.Noninterference
	base["schedules_sha256"] = t.Schedules
	base["harm_bound_sha256"] = t.HarmBound
	base["harm_upper_ppm"] = t.HarmUpperPPM
	base["policy_version"] = t.Policy
	base["epoch"] = t.Epoch
	canonical, _ := jsonMap(base)
	base["signature_ed25519_hex"] = hex.EncodeToString(ed25519.Sign(g.signer, canonical))
	return base
}
func (g *gateway) handle(raw []byte) map[string]any {
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.poisoned {
		return g.signed("PERSISTENCE_FAILED")
	}
	w, payload, err := parse(raw)
	if err != nil {
		return g.signed("INVALID_FRAME")
	}
	if w.T != g.tenant {
		return g.signed("TENANT_REJECTED")
	}
	if g.nonces[w.N] || w.S < g.next {
		return g.signed("REPLAY_REJECTED")
	}
	if w.S != g.next {
		return g.signed("OUT_OF_ORDER")
	}
	if w.Issued < g.last {
		return g.signed("CLOCK_REGRESSION")
	}
	if w.Expires < w.Issued {
		return g.signed("EXPIRED")
	}
	if g.next >= 1024 {
		return g.signed("CAPACITY_EXHAUSTED")
	}
	b, err := canonicalBody(payload)
	if err != nil {
		return g.signed("INVALID_BODY")
	}
	if w.C == "E" && b.Kind == "allow" {
		return g.signed("DENY_CLIENT_ALLOW")
	}
	if w.C == "E" && b.Kind == "veto" {
		if !g.withPersistence(func() {
			g.capMask = 0
			g.phase = "LOCKDOWN"
			g.nonces[w.N] = true
			g.next++
			g.last = w.Issued
		}) {
			return g.signed("PERSISTENCE_FAILED")
		}
		return g.signed("LOCKDOWN")
	}
	if g.phase == "LOCKDOWN" {
		return g.signed("LOCKDOWN")
	}
	before := g.snapshot()
	code := "POLICY_REJECTED"
	switch {
	case g.phase == "IDLE" && w.C == "A" && b.Kind == "observe" && b.Cap == nil && !b.Alarm:
		g.phase = "OBSERVED"
		code = "OBSERVED"
	case g.phase == "OBSERVED" && w.C == "B" && b.Kind == "assess" && b.Cap == nil && !b.Alarm:
		g.phase = "ASSESSED"
		code = "ASSESSED"
	case g.phase == "ASSESSED" && w.C == "D" && b.Kind == "propose" && b.Cap != nil && *b.Cap == "compute" && !b.Alarm:
		if b.Attestation == nil {
			return g.signed("DENY_UNATTESTED")
		}
		if !g.checkAttestation(b.Attestation, w.Issued) {
			return g.signed("DENY_BAD_ATTESTATION")
		}
		g.capMask &= 2
		g.phase = "MODEL_APPROVED"
		code = "MODEL_APPROVED"
	case g.phase == "ASSESSED" && w.C == "C" && b.Kind == "propose":
		return g.signed("DENY_UNATTESTED")
	}
	if code == "POLICY_REJECTED" {
		return g.signed(code)
	}
	g.nonces[w.N] = true
	g.next++
	g.last = w.Issued
	if err := g.persist(); err != nil {
		g.restore(before)
		g.capMask = 0
		g.phase = "LOCKDOWN"
		g.poisoned = true
		return g.signed("PERSISTENCE_FAILED")
	}
	if code == "MODEL_APPROVED" && b.Attestation != nil {
		return g.signedDFX(code, w, b.Attestation)
	}
	return g.signed(code)
}
func serve(g *gateway, con net.Conn) {
	defer con.Close()
	if err := con.SetDeadline(time.Now().Add(3 * time.Second)); err != nil {
		return
	}
	size := make([]byte, 4)
	if _, err := io.ReadFull(con, size); err != nil {
		return
	}
	n := binary.BigEndian.Uint32(size)
	var result map[string]any
	if n > 8192 || n == 0 {
		g.mu.Lock()
		result = g.signed("INVALID_FRAME")
		g.mu.Unlock()
	} else {
		raw := make([]byte, n)
		if _, err := io.ReadFull(con, raw); err != nil {
			return
		}
		result = g.handle(raw)
	}
	serialized, _ := jsonMap(result)
	header := make([]byte, 4)
	binary.BigEndian.PutUint32(header, uint32(len(serialized)))
	_, _ = con.Write(append(header, serialized...))
}
func main() {
	sock := flag.String("socket", "", "Unix domain socket path")
	tenant := flag.String("tenant", "", "Bound tenant")
	pub := flag.String("trusted-key", "", "External offline Ed25519 verifier key")
	shell := flag.String("shell", "", "SHA256 static shell")
	secret := flag.String("receipt-key-file", "", "Private audit-receipt seed file")
	stateFile := flag.String("state-file", "", "Mandatory signed state checkpoint file")
	bootstrap := flag.Bool("bootstrap", false, "Explicit first provisioning of a new state file")
	flag.Parse()
	if *sock == "" || *stateFile == "" || !ident.MatchString(*tenant) || !hex64.MatchString(*shell) {
		fmt.Fprintln(os.Stderr, "configuration invalid")
		os.Exit(2)
	}
	pubbytes, e1 := hex.DecodeString(*pub)
	seedbytes, e2 := regularPrivateFile(*secret)
	if e1 != nil || e2 != nil || len(pubbytes) != ed25519.PublicKeySize {
		fmt.Fprintln(os.Stderr, "missing external trust key")
		os.Exit(2)
	}
	seed, e3 := hex.DecodeString(strings.TrimSpace(string(seedbytes)))
	if e3 != nil || len(seed) != ed25519.SeedSize {
		fmt.Fprintln(os.Stderr, "invalid local signing key")
		os.Exit(2)
	}
	// Test adapter: real native process, but same UID as the caller; NOT a hardware TCB.
	g := &gateway{tenant: *tenant, shell: *shell, trusted: ed25519.PublicKey(pubbytes),
		signer: ed25519.NewKeyFromSeed(seed), nonces: make(map[string]bool), capMask: 7, phase: "IDLE", epoch: 1,
		stateFile: *stateFile}
	if *bootstrap {
		if _, err := os.Lstat(*stateFile + ".anchor"); err == nil {
			fmt.Fprintln(os.Stderr, "state anchor already exists; bootstrap rejected")
			os.Exit(2)
		} else if !os.IsNotExist(err) {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		if _, err := os.Lstat(*stateFile); err == nil {
			fmt.Fprintln(os.Stderr, "state file already exists; bootstrap rejected")
			os.Exit(2)
		} else if !os.IsNotExist(err) {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		if err := g.persist(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
	} else {
		if err := g.loadState(); err != nil {
			fmt.Fprintln(os.Stderr, "fail-closed state recovery:", err)
			os.Exit(2)
		}
	}
	listener, err := net.Listen("unix", *sock)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	defer listener.Close()
	if err := os.Chmod(*sock, 0600); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	for {
		con, err := listener.Accept()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return
		}
		go serve(g, con)
	}
}
