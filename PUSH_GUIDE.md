# Git Push 指南

## 一键推送

```bash
cd D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1
git push origin main
```

## 连接方式（2026-08-21 实测结论）

**直连优先，代理兜底。**

- ✅ **直连（默认）**：`ssh.github.com:443` 国内直连可达，速度快（97MB 约 45 秒）
- ⚠️ **代理隧道慢**：经 Clash (`connect -H/-S 127.0.0.1:7897`) 时仅 ~100KB/s，97MB 需 17 分钟且易断流，**勿用**（connect.exe 老工具吞吐瓶颈）
- 若直连失败（如网络变化），取消 `~/.ssh/config` 中 ProxyCommand 行的注释恢复代理

### SSH 配置（`~/.ssh/config`）

```
Host github.com
  HostName ssh.github.com
  Port 443
  User git
  IdentityFile C:\Users\Administrator\.ssh\id_ed25519_neurograph
  IdentitiesOnly yes
  # 直连失败时恢复: ProxyCommand connect -S 127.0.0.1:7897 %h %p
```

> 注意：`known_hosts` 需含 `[ssh.github.com]:443` 条目（已配置）。直连与走代理解析到同一台服务器，host key 相同。

### SSH 密钥

| 文件 | 用途 | 状态 |
|------|------|------|
| `~/.ssh/id_ed25519_neurograph` | **当前使用的私钥** | ✅ 正常 |
| `~/.ssh/id_ed25519_neurograph.pub` | 对应公钥，已添加至 GitHub | ✅ 已授权 |
| `~/.ssh/id_ed25519` | 私钥已损坏（内容是 fingerprint，非真实密钥） | ❌ 勿用 |

### 远端仓库

```
git@github.com:feezy777/NeuroGraphIQ_KG.git
```
