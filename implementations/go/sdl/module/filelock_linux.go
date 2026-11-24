package module

import (
	"context"
	"errors"
	"os"
	"syscall"
	"time"
)

// Kernel locks survive neither process death nor descriptor closure. A timeout
// never steals a lock from another writer.
func lockFile(ctx context.Context, root *os.Root, name string) (*os.File, error) {
	if err := ctx.Err(); err != nil {
		return nil, operational(err)
	}
	file, err := root.OpenFile(name, os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return nil, operational(err)
	}
	before, err := root.Lstat(name)
	opened, statErr := file.Stat()
	if err != nil || statErr != nil || !opened.Mode().IsRegular() || !os.SameFile(before, opened) {
		_ = file.Close()
		return nil, invalid()
	}
	bounded, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	ticker := time.NewTicker(10 * time.Millisecond)
	defer ticker.Stop()
	for {
		if canceled := bounded.Err(); canceled != nil {
			_ = file.Close()
			return nil, operational(canceled)
		}
		err = syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			return file, nil
		}
		if !errors.Is(err, syscall.EWOULDBLOCK) && !errors.Is(err, syscall.EAGAIN) {
			_ = file.Close()
			return nil, operational(err)
		}
		select {
		case <-bounded.Done():
			_ = file.Close()
			return nil, operational(bounded.Err())
		case <-ticker.C:
		}
	}
}
