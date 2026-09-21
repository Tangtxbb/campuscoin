# -*- coding: utf-8 -*-
"""
最小智能合约：一个栈式脚本虚拟机（mini Script VM）。

这不是完整的 EVM，而是一个能表达"可编程的花钱条件"的最小系统，
支持两类经典合约：

1. 多重签名（m-of-n）：一笔钱需要 n 个公钥中任意 m 个签名才能花。
   锁定脚本： ["PUSH", pub1, "PUSH", pub2, "PUSH", pub3, "CHECKMULTISIG", "2", "3"]
   解锁脚本： ["PUSH", sig1, "PUSH", sig2]

2. 时间锁：钱锁定到某个时间戳之后才能花。
   锁定脚本： ["PUSH", locktime, "CHECKLOCKTIME", "PUSH", pub, "CHECKSIG"]
   解锁脚本： ["PUSH", sig]

脚本是一串 token（字符串），其中 "PUSH" 后面跟一个十六进制数据。
执行模型：先运行解锁脚本把数据压栈，再运行锁定脚本消费栈并校验。
"""

import hashlib
import time

from ecdsa import BadSignatureError, SECP256k1, VerifyingKey


class _ScriptFail(Exception):
    """脚本执行失败（验签失败、条件不满足等）。"""


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _check_sig(pub_hex: str, sig_hex: str, sighash: str) -> bool:
    """验证签名是否由公钥对 sighash 生成。"""
    try:
        vk = VerifyingKey.from_string(bytes.fromhex(pub_hex), curve=SECP256k1)
        return vk.verify(bytes.fromhex(sig_hex), sighash.encode("utf-8"))
    except (BadSignatureError, Exception):
        return False


def _pop(stack):
    if not stack:
        raise _ScriptFail()
    return stack.pop()


def _exec(script, stack, ctx):
    """执行一段脚本，直接修改传入的栈。"""
    i = 0
    while i < len(script):
        op = script[i]
        if op == "PUSH":
            i += 1
            stack.append(bytes.fromhex(script[i]))
        elif op == "DUP":
            stack.append(stack[-1] if stack else b"")
        elif op == "HASH":
            stack.append(_sha256(_pop(stack)))
        elif op == "EQUAL":
            a, b = _pop(stack), _pop(stack)
            stack.append(a == b)
        elif op == "EQUALVERIFY":
            if _pop(stack) != _pop(stack):
                raise _ScriptFail()
        elif op == "VERIFY":
            if not _pop(stack):
                raise _ScriptFail()
        elif op == "CHECKSIG":
            pub = _pop(stack)
            sig = _pop(stack)
            stack.append(_check_sig(pub.hex(), sig.hex(), ctx["sighash"]))
        elif op == "CHECKMULTISIG":
            m = int(script[i + 1])
            n = int(script[i + 2])
            i += 2
            pubs = [_pop(stack) for _ in range(n)][::-1]
            sigs = [_pop(stack) for _ in range(m)][::-1]
            valid = 0
            used = set()
            for s in sigs:
                for j, p in enumerate(pubs):
                    if j in used:
                        continue
                    if _check_sig(p.hex(), s.hex(), ctx["sighash"]):
                        valid += 1
                        used.add(j)
                        break
            stack.append(valid >= m)
        elif op == "CHECKLOCKTIME":
            lock = int.from_bytes(_pop(stack), "big")
            if ctx["now"] < lock:
                raise _ScriptFail()     # 时间未到，锁定中
        elif op == "DROP":
            _pop(stack)
        else:
            raise _ScriptFail()
        i += 1


def run_script(lock_script, unlock_script, context=None) -> bool:
    """执行锁定+解锁脚本，返回该输出是否可被花费。

    context 需包含：
      - sighash: 交易签名哈希（十六进制），CHECKSIG 用它验签
      - now:     当前时间戳（毫秒），CHECKLOCKTIME 用它判断时间锁
    """
    ctx = context or {}
    ctx.setdefault("now", int(time.time() * 1000))
    stack = []
    try:
        _exec(unlock_script, stack, ctx)
        _exec(lock_script, stack, ctx)
    except (_ScriptFail, IndexError, ValueError):
        return False
    if not stack:
        return False
    top = stack[-1]
    if isinstance(top, bool):
        return top
    if isinstance(top, bytes):
        return len(top) > 0 and top != b"\x00"
    return bool(top)


# ---------------- 便捷构造器 ----------------

def multisig_lock(pubkeys_hex: list, m: int) -> list:
    """构造 m-of-n 多签锁定脚本。"""
    n = len(pubkeys_hex)
    script = []
    for p in pubkeys_hex:
        script += ["PUSH", p]
    script += ["CHECKMULTISIG", str(m), str(n)]
    return script


def timelock_lock(pubkey_hex: str, locktime_ms: int) -> list:
    """构造时间锁锁定脚本：locktime_ms 之后才能由 pubkey 花费。"""
    return ["PUSH", locktime_ms.to_bytes(8, "big").hex(),
            "CHECKLOCKTIME", "PUSH", pubkey_hex, "CHECKSIG"]
