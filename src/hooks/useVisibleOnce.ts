import { useEffect, useRef, useState } from "react";

/**
 * ref 로 지정한 요소가 뷰포트(rootMargin 만큼 확장) 안에 처음 들어오면 visible 을
 * true 로 바꾸고 관찰을 멈춘다. 대형 정적 JSON 의 섹션 진입 시 지연 로드 트리거 용도.
 * IntersectionObserver 미지원 환경(jsdom 등)에서는 즉시 로드로 폴백한다.
 * active 가 false 인 동안(예: ref 대상이 아직 렌더되지 않음)은 관찰을 미룬다.
 */
export function useVisibleOnce<T extends Element>(rootMargin = "0px", active = true) {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!active || visible) return;
    const element = ref.current;
    if (typeof IntersectionObserver === "undefined" || !element) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
        }
      },
      { rootMargin }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [active, visible, rootMargin]);

  return { ref, visible };
}
