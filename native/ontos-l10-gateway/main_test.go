package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func testGateway(t *testing.T) *gateway {
	t.Helper()
	digest := sha256.Sum256([]byte("test-only-native-gateway-secret"))
	signer := ed25519.NewKeyFromSeed(digest[:])
	name := filepath.Join(t.TempDir(), "state.json")
	g := &gateway{tenant: "tenant-a", shell: hex.EncodeToString(digest[:]), trusted: signer.Public().(ed25519.PublicKey),
		signer: signer, nonces: map[string]bool{}, capMask: 7, phase: "IDLE", epoch: 1, stateFile: name}
	if err := g.persist(); err != nil {
		t.Fatal(err)
	}
	return g
}
func wireFor(t *testing.T, channel, nonce string, seq uint32) []byte {
	t.Helper()
	payload := []byte(`{"alarm":false,"cap":null,"kind":"observe"}`)
	w := wire{V: "ontos-ipc-v1", C: channel, T: "tenant-a", N: nonce, S: seq, Issued: uint64(seq + 1), Expires: 200}
	w.Payload = "eyJhbGFybSI6ZmFsc2UsImNhcCI6bnVsbCwia2luZCI6Im9ic2VydmUifQ=="
	_ = payload
	core, _ := jsonMap(coreFields(w))
	digest := sha256.Sum256(core)
	w.Checksum = hex.EncodeToString(digest[:])
	all := coreFields(w)
	all["checksum"] = w.Checksum
	result, e := jsonMap(all)
	if e != nil {
		t.Fatal(e)
	}
	return result
}
func TestSignedCheckpointRejectsTamper(t *testing.T) {
	g := testGateway(t)
	if resp := g.handle(wireFor(t, "A", "a", 0)); resp["status"] != "OBSERVED" {
		t.Fatal(resp)
	}
	again := testGateway(t)
	again.stateFile = g.stateFile
	again.shell = g.shell
	again.signer = g.signer
	if err := again.loadState(); err != nil {
		t.Fatal(err)
	}
	if again.next != 1 || again.phase != "OBSERVED" {
		t.Fatal("signed replay state lost")
	}
	data, err := os.ReadFile(g.stateFile)
	if err != nil {
		t.Fatal(err)
	}
	data[len(data)/2] ^= 1
	if err = os.WriteFile(g.stateFile, data, 0600); err != nil {
		t.Fatal(err)
	}
	if err = again.loadState(); err == nil {
		t.Fatal("tampered durable state passed")
	}
}
func TestConcurrentOversizeAndUpdatesHasNoRace(t *testing.T) {
	g := testGateway(t)
	var wg sync.WaitGroup
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			a, b := net.Pipe()
			defer a.Close()
			defer b.Close()
			done := make(chan struct{})
			go func() { serve(g, b); close(done) }()
			header := make([]byte, 4)
			binary.BigEndian.PutUint32(header, 9000)
			if _, err := a.Write(header); err != nil {
				t.Error(err)
			}
			response := make([]byte, 4)
			if _, err := a.Read(response); err != nil {
				t.Error(err)
			}
			<-done
		}()
	}
	wg.Add(1)
	go func() {
		defer wg.Done()
		if resp := g.handle(wireFor(t, "A", "obs", 0)); resp["status"] != "OBSERVED" {
			t.Error(resp)
		}
	}()
	wg.Wait()
}
