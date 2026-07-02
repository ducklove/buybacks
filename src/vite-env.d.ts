/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 실시간 시세 프록시(kis_proxy) 주소. 비어 있으면 실시간 시세 기능이 비활성화됩니다. */
  readonly VITE_KIS_PROXY_URL?: string;
  /** 네이버금융 프록시 주소. 설정 시 VITE_KIS_PROXY_URL보다 우선합니다. */
  readonly VITE_NAVERFINANCE_PROXY_URL?: string;
}
