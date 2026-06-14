# ctfsafe/encryption.py
# -*- coding: utf-8 -*-
"""
题库加密存储工具
使用 Fernet (AES-128-CBC + HMAC) 对 flag 和答案进行加密存储
"""
import os
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """加密/解密失败"""
    pass


def _get_fernet():
    """
    获取 Fernet 实例。
    密钥优先级：
    1. FERNET_KEY 环境变量（推荐生产使用）
    2. 从 SECRET_KEY 派生（开发环境回退）
    """
    fernet_key = os.environ.get('FERNET_KEY', '')
    if fernet_key:
        try:
            return Fernet(fernet_key.encode())
        except Exception as e:
            logger.error(f"FERNET_KEY 无效: {e}")
            raise EncryptionError("FERNET_KEY 配置错误")

    # 开发环境：从 SECRET_KEY 派生一个 32-byte base64 key
    secret = settings.SECRET_KEY.encode()
    derived = hashlib.sha256(secret).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def encrypt_field(plaintext: str) -> str:
    """
    加密字段值（用于存储到数据库）
    返回 base64 字符串
    """
    if not plaintext:
        return ''
    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(plaintext.encode('utf-8'))
        return encrypted.decode('utf-8')
    except EncryptionError:
        raise
    except Exception as e:
        logger.error(f"加密失败: {e}")
        raise EncryptionError(f"加密失败: {e}")


def decrypt_field(ciphertext: str) -> str:
    """
    解密字段值（从数据库读取后）
    返回原文
    """
    if not ciphertext:
        return ''
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(ciphertext.encode('utf-8'))
        return decrypted.decode('utf-8')
    except InvalidToken:
        logger.error("解密失败：密钥不匹配或数据已损坏")
        raise EncryptionError("解密失败：密钥不匹配或数据已损坏")
    except EncryptionError:
        raise
    except Exception as e:
        logger.error(f"解密失败: {e}")
        raise EncryptionError(f"解密失败: {e}")


def generate_fernet_key():
    """生成一个新的 Fernet 密钥（供部署时使用）"""
    return Fernet.generate_key().decode('utf-8')
