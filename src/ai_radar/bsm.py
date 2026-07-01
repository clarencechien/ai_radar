"""Black-Scholes-Merton 封閉解(call)。

純數學,無外部相依(只用 stdlib math)。
- 定價 + Greeks:delta(槓桿透鏡)、gamma/vega(凸性透鏡)、theta。
- IV 反解:給市場價回推隱含波動(yfinance 的 IV 不可信時自算)。
慣例:σ、r 為年化小數;T 為年;vega/theta 提供「每 1% / 每日」的實用單位。
"""
from __future__ import annotations

import math

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def _d1_d2(S, K, T, r, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        raise ValueError("S,K,T,sigma 必須為正")
    vol_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_t
    return d1, d1 - vol_t


def call_price(S, K, T, r, sigma, q=0.0) -> float:
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def greeks(S, K, T, r, sigma, q=0.0) -> dict:
    """回傳 call 的 delta / gamma / vega(每1%) / theta(每日) / price。"""
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_q = math.exp(-q * T)
    pdf = _norm_pdf(d1)
    delta = disc_q * _norm_cdf(d1)
    gamma = disc_q * pdf / (S * sigma * math.sqrt(T))
    vega = S * disc_q * pdf * math.sqrt(T)                 # 每 1.0 vol
    theta_year = (
        -(S * disc_q * pdf * sigma) / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * _norm_cdf(d2)
        + q * S * disc_q * _norm_cdf(d1)
    )
    return {
        "price": call_price(S, K, T, r, sigma, q),
        "delta": delta,
        "gamma": gamma,
        "vega": vega / 100.0,        # 每 1% vol
        "theta": theta_year / 365.0,  # 每日
    }


def implied_vol(price, S, K, T, r, q=0.0, lo=1e-4, hi=5.0, tol=1e-6, max_iter=100):
    """由市場價反解 IV(bisection,穩健)。無解回 None。"""
    intrinsic = max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0)
    if price < intrinsic - 1e-9 or price <= 0:
        return None  # 低於內含價值 → 無有效 IV
    f_lo = call_price(S, K, T, r, lo, q) - price
    f_hi = call_price(S, K, T, r, hi, q) - price
    if f_lo * f_hi > 0:
        return None  # 區間內無根(價格超出可解範圍)
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = call_price(S, K, T, r, mid, q) - price
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
