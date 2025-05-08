# ByteCTF2024-Final-C2

Winning solution for ByteCTF2024 Masters "Blue Team - Hidden Channel". A cross-platform, multi-channel C2 (Command and Control) communication framework based on Feishu (Lark), WeChat, DingTalk, and GitHub, designed for communication-restricted scenarios.

## Project Goals

* Implement Command and Control (C2) communication based on enterprise communication platforms (Feishu/Lark, WeChat Work, DingTalk, GitHub)
* Support core features including command execution, file transfer, socks5 tunneling
* Compatible with Windows/Linux/macOS platforms
* Support high-speed file transfer and persistent session management

## Dependencies

* [gost](https://github.com/go-gost/gost): For providing socks5 service
* [File-Tunnel](https://github.com/fiddyschmitt/File-Tunnel): For encapsulating TCP streams as files for transmission to evade network detection

## System Architecture

The system is divided into three layers:

1. Communication Layer: Handles bot API communication, token management, group chat management, etc.
2. Command Processing Layer: Includes command parsing, routing, execution, result packaging, etc.
3. File Operation Layer: Manages directory operations, file read/write, upload/download tasks

## Communication Channel Design

| Platform | Channel Mechanism | Implementation Features |
| --- | --- | --- |
| **Feishu/Lark** | Rich text push-pull interface | Supports interactive shell, high-speed file synchronization (>100MB/s), file channel to TCP conversion |
| **GitHub** | Repository file read/write | Can manage multiple controlled endpoints simultaneously, supports session management and interactive command execution |
| **DingTalk** | WSS bidirectional streaming | Implements basic C2 functionality |
| **WeChat Work** | Webhook + public account article interface | Webhook can be used for issuing commands, uses public account article interface to bypass receiving restrictions |

## Core Functional Modules

- [x] Command execution
- [x] File operations
- [x] socks5 proxy
- [x] Multi-client management

## Improvement Directions

* Codes are only used to verify C2 communication concepts and cannot be directly used in real-world scenarios
* Current file-tunnel TCP forwarding mechanism has a 0.5~1s delay, multiple socks5 handshakes cause overall throughput reduction
* Communication methods based on open APIs are easily restricted by platform QPS limitations