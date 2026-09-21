#!/usr/bin/env python3
"""
华之星后台 API 客户端 —— 复用已验证的登录 / 二级待办 / 上传证书 接口。
纯 requests 实现，路径与服务地址均参数化。
"""
import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("hzx")


class HzxClient:
    def __init__(self, username: str, password: str, base_url: str):
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json, text/plain, */*"})

    def login(self) -> None:
        url = f"{self.base_url}/appservice/login"
        logger.info("登录华之星后台：%s", url)
        resp = self.session.post(
            url,
            json={"username": self.username, "password": self.password, "code": "", "uuid": ""},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"登录失败：{data}")
        self.token = data["data"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        logger.info("登录成功")

    def get_secondary_orders(self, page_size: int = 200) -> List[Dict]:
        """分页拉取全部二级待办（默认每页 200，超出自动翻页，避免漏匹配）。"""
        url = f"{self.base_url}/appservice/hyz/ServiceOrderRecord/getUploadCertList"
        all_orders: List[Dict] = []
        page = 1
        while True:
            resp = self.session.get(
                url, params={"pageNum": page, "pageSize": page_size}, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 200:
                raise RuntimeError(f"获取二级待办列表失败：{data}")
            result = data["data"]["result"]
            all_orders.extend(result)
            if len(result) < page_size:
                break
            page += 1
        return all_orders

    def upload_certificate(self, order: Dict, files: List[Tuple[str, str, str]],
                           max_retries: int = 3, backoff: float = 2.0) -> Dict:
        """
        上传证书到指定订单，带重试与退避（防限流/网络抖动）。
        - 401：token 失效，自动重新登录后重试一次。
        - 429/5xx/超时/连接错误：按指数退避重试。
        """
        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return self._do_upload(order, files)
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 401:
                    logger.warning("登录态失效(401)，重新登录后重试")
                    self.token = None
                    self.login()
                    continue
                if status in (429, 500, 502, 503, 504):
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning("上传遇 %s，%.1fs 后重试(%d/%d)",
                                   status, wait, attempt, max_retries)
                    time.sleep(wait)
                    continue
                raise
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                wait = backoff * (2 ** (attempt - 1))
                logger.warning("网络异常 %s，%.1fs 后重试(%d/%d)",
                               e, wait, attempt, max_retries)
                time.sleep(wait)
                continue
        raise RuntimeError(f"上传重试 {max_retries} 次仍失败：{last_err}")

    def _do_upload(self, order: Dict, files: List[Tuple[str, str, str]]) -> Dict:
        """单次实际上传（不含重试）。files: [(文件名, 本地路径, 证书号), ...]"""
        url = f"{self.base_url}/appservice/hyz/Servicecertificate/uploadCert"
        form: Dict[str, str] = {}
        form["recordData"] = json.dumps(order, ensure_ascii=False)

        no_list = []
        for filename, _path, cert_no in files:
            no_list.append({filename: cert_no})
        form["certificateNOList"] = json.dumps(no_list, ensure_ascii=False)
        form["remark"] = form["certificateNOList"]

        mfiles = [
            ("cert", (os.path.basename(p), open(p, "rb"), "application/pdf"))
            for _f, p, _c in files
        ]
        try:
            resp = self.session.post(url, data=form, files=mfiles, timeout=60)
            resp.raise_for_status()
            return resp.json()
        finally:
            for _n, fobj, _t in mfiles:
                fobj.close()
