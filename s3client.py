#!/usr/bin/env python3
# Copyright (c) 2026 Jose-AI · 恒忆 Evermem (pmem) · 版权所有
# 仓库: https://github.com/linhut/evermem
# 官网: https://www.linhut.cn
# 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）

# pmem s3client - 零依赖 S3 兼容客户端（AWS SigV4），用于恒忆加密归档包上传/下载
#
#
# 目标：阿里云 OSS / 腾讯云 COS / AWS S3 / MinIO / 百度智能云 BOS 等 S3 兼容存储。
# 只实现备份所需的最小面：put/get/head/list/delete + 连通性测试，单请求直传（无分片）。
# 全部走标准库（urllib/hmac/hashlib），不依赖 boto3。
#
# 用法：
#   c = S3Client(endpoint="https://oss-cn-hangzhou.aliyuncs.com", access_key="AK",
#                secret_key="SK", region="cn-hangzhou", bucket="evermem-backup", prefix="archive")
#   c.test()                      # 连通/凭证探测（ListObjectsV2 最小查询）
#   c.put_object("2026/evermem.tar.aes", data_bytes)
#   c.get_object("2026/evermem.tar.aes") -> bytes
#   c.list_objects("2026/") -> [keys]
#   c.head_object(key) -> bool
#   c.delete_object(key)
#
# 说明：路径式寻址（/bucket/key），兼容 OSS/COS/MinIO/BOS；
#       AWS 新区域（2020 后）要求虚拟主机式寻址，如遇 400/301 请改用 endpoint 为 `<bucket>.s3.<region>.amazonaws.com` 形式。

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request

_AWS4 = "aws4_request"
_ALGO = "AWS4-HMAC-SHA256"

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class S3Error(Exception):
    def __init__(self, status: int, body: str, key: str = ""):
        self.status = status
        self.body = body[:500]
        self.key = key
        super().__init__(f"S3 {status} {body[:200]}" + (f" (@{key})" if key else ""))

class S3Client:
    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 region: str = "auto", bucket: str = "", prefix: str = "",
                 timeout: int = 60):
        endpoint = (endpoint or "").strip().rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            endpoint = "https://" + endpoint
        self.endpoint = endpoint
        self.access_key = access_key or ""
        self.secret_key = secret_key or ""
        self.region = region or "us-east-1"
        self.bucket = (bucket or "").strip().strip("/")
        self.prefix = (prefix or "").strip().strip("/")
        self.timeout = timeout

    # ---------- 内部：SigV4 ----------

    @staticmethod
    def _amz_date() -> tuple[str, str]:
        now = datetime.datetime.now(datetime.timezone.utc)
        return now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")

    def _canonical_request(self, method: str, uri_path: str, query: str,
                           headers: dict[str, str], payload_hash: str) -> str:
        c_headers = {k.lower(): str(v).strip() for k, v in headers.items()}
        s_headers = ";".join(sorted(c_headers))
        c_hdr = "".join(f"{k}:{c_headers[k]}\n" for k in sorted(c_headers))
        return "\n".join([method, uri_path, query, c_hdr, s_headers, payload_hash])

    def _request(self, method: str, key: str, query: dict | None = None,
                 headers: dict | None = None, body: bytes = b"") -> bytes:
        headers = dict(headers or {})
        query = dict(query or {})
        payload_hash = _sha256_hex(body)
        amz_date, datestamp = self._amz_date()
        path = "/" + self.bucket + ("/" + key if key else "")
        netloc = urllib.parse.urlparse(self.endpoint).netloc
        headers.setdefault("Host", netloc)
        headers.setdefault("x-amz-content-sha256", payload_hash)
        headers.setdefault("x-amz-date", amz_date)
        c_query = "&".join(f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
                           for k, v in sorted(query.items()))
        # 路径中的 key 分段逐段 quote，保留 "/"
        uri_path = "/".join(urllib.parse.quote(seg, safe="-_.~") for seg in path.split("/"))
        creq = self._canonical_request(method, uri_path, c_query, headers, payload_hash)
        scope = f"{datestamp}/{self.region}/s3/{_AWS4}"
        sts = "\n".join([_ALGO, amz_date, scope, _sha256_hex(creq.encode("utf-8"))])
        k = _sign(("AWS4" + self.secret_key).encode("utf-8"), datestamp)
        k = _sign(k, self.region)
        k = _sign(k, "s3")
        k = _sign(k, _AWS4)
        sig = hmac.new(k, sts.encode("utf-8"), hashlib.sha256).hexdigest()
        s_headers = sorted(h.lower() for h in headers)
        auth = (f"{_ALGO} Credential={self.access_key}/{scope}, "
                f"SignedHeaders={';'.join(s_headers)}, Signature={sig}")
        headers["Authorization"] = auth
        headers.pop("Host", None)  # urllib 自己填 Host
        url = f"{self.endpoint}{uri_path}" + (f"?{c_query}" if c_query else "")
        req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None,
                                     method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise S3Error(exc.code, exc.read().decode("utf-8", "replace"), key) from None

    # ---------- 对外 ----------

    def test(self) -> dict:
        """连通性与凭证探测：ListObjectsV2 前 1 条。"""
        if not (self.endpoint and self.access_key and self.secret_key and self.bucket):
            return {"ok": False, "error": "endpoint/AK/SK/bucket 均必填"}
        try:
            data = self._request("GET", "", {"list-type": "2", "max-keys": "1"})
            return {"ok": True, "msg": f"连接成功（{self.endpoint} / {self.bucket}）"}
        except S3Error as exc:
            if exc.status == 404:
                # 部分实现 bucket 不存在会 404，但 OSS/COS 通常 403；提示用户检查 bucket
                return {"ok": False, "error": f"bucket 不存在或无权限：{exc.body}"}
            return {"ok": False, "error": str(exc)}

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> int:
        self._request("PUT", self._full_key(key),
                      headers={"Content-Type": content_type}, body=data)
        return len(data)

    def get_object(self, key: str) -> bytes:
        return self._request("GET", self._full_key(key))

    def head_object(self, key: str) -> bool:
        try:
            self._request("HEAD", self._full_key(key))
            return True
        except S3Error:
            return False

    def list_objects(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        token = ""
        pfx = f"{self.prefix}/{prefix}" if self.prefix else prefix
        while True:
            q = {"list-type": "2", "prefix": pfx, "max-keys": "1000"}
            if token:
                q["continuation-token"] = token
            data = self._request("GET", "", q)
            keys += [c["Key"] for c in json.loads(self._xml2json(data).get("Contents", []))]
            token = self._xml2json(data).get("NextContinuationToken", "")
            if not token:
                break
        return keys

    def delete_object(self, key: str, raw: bool = False) -> None:
        # raw=True：key 已含 prefix（如 list_objects 的返回），不再二次拼接。
        # 原实现总是再拼一次 prefix，导致"云端旧包永不清理且日志谎报已清理"。
        self._request("DELETE", key if raw else self._full_key(key))

    @staticmethod
    def _xml2json(data: bytes) -> dict:
        """ListBucketResult 的最小解析（标准库无 xml→dict，用正则取条目标签）。"""
        import re
        text = data.decode("utf-8", "replace")
        out: dict = {}
        for tag in ("IsTruncated", "NextContinuationToken"):
            m = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
            if m:
                out[tag] = m.group(1)
        contents: list[dict] = []
        for block in re.findall(r"<Contents>(.*?)</Contents>", text, re.S):
            k = re.search(r"<Key>([^<]*)</Key>", block)
            s = re.search(r"<Size>([^<]*)</Size>", block)
            if k:
                contents.append({"Key": k.group(1), "Size": int(s.group(1)) if s else 0})
        out["Contents"] = contents
        return out

if __name__ == "__main__":
    import sys

    ep = os.environ.get("PMEM_S3_ENDPOINT", "")
    ak = os.environ.get("PMEM_S3_AK", "")
    sk = os.environ.get("PMEM_S3_SK", "")
    bk = os.environ.get("PMEM_S3_BUCKET", "")
    if not (ep and ak and sk and bk):
        print("用法：PMEM_S3_ENDPOINT / PMEM_S3_AK / PMEM_S3_SK / PMEM_S3_BUCKET（可选 PMEM_S3_REGION）设置后运行测试")
        sys.exit(1)
    c = S3Client(ep, ak, sk, os.environ.get("PMEM_S3_REGION", "us-east-1"), bk)
    print(json.dumps(c.test(), ensure_ascii=False))
