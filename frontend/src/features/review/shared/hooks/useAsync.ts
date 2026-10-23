import { useCallback, useEffect, useRef, useState } from 'react';

interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
}

function sameDeps(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
}

/**
 * 비동기 함수를 호출하고 결과, 오류, 로딩 상태를 돌려줍니다. deps가 바뀌거나 reload()를 부르면 다시 호출합니다.
 * 다시 불러오는 동안에는 이전 data를 유지해서 화면이 깜박이지 않게 합니다.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: readonly unknown[]) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  const [prevDeps, setPrevDeps] = useState(deps);
  const fnRef = useRef(fn);

  // 최신 함수를 effect에서 읽을 수 있게 effect 안에서 ref를 갱신합니다(렌더 중 ref 쓰기 금지).
  useEffect(() => {
    fnRef.current = fn;
  });

  // deps가 바뀌면 렌더 중에 로딩 상태로 되돌립니다(이전 렌더 값을 근거로 한 조건부 갱신).
  if (!sameDeps(prevDeps, deps)) {
    setPrevDeps(deps);
    setState((prev) => ({ ...prev, loading: true, error: null }));
  }

  useEffect(() => {
    let alive = true;
    fnRef
      .current()
      .then((data) => {
        if (alive) setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (alive) setState((prev) => ({ data: prev.data, error, loading: false }));
      });
    return () => {
      alive = false;
    };
    // deps는 호출하는 쪽이 정한 배열이라 spread로 넘깁니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    setTick((value) => value + 1);
  }, []);
  return { ...state, reload };
}
