// [개발 확인용 임시 코드] 시안 비교용 목업 시작 상태. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { mockApi } from '../features/review/shared/api';
import { createMockState, type MockState } from '../features/review/shared/api/mock/fixtures';
import { devParam } from './params';

/** ?mock=many 에서 만드는 문서 수. 한 페이지(100건)를 넘겨 이전/다음과 total 표시를 확인합니다. */
const MANY_DOCS = 105;

/**
 * 기본 목업 문서를 복제해 보이는 문서가 MANY_DOCS건이 되도록 채웁니다. 복제본은 원본보다 오래된 업로드 일시를 갖고
 * 문서 ID와 로트 번호, 파일명만 다릅니다(상태, 판정, 항목은 원본과 같습니다).
 */
function addManyDocs(state: MockState): void {
  const base = state.docs.filter((doc) => !doc.hidden);
  const oldest = Math.min(...base.map((doc) => Date.parse(doc.detail.uploaded_at)));
  for (let n = 1; base.length + n - 1 < MANY_DOCS; n += 1) {
    const copy = structuredClone(base[(n - 1) % base.length]);
    const id = `dummy-${String(n).padStart(3, '0')}`;
    copy.detail.document_id = id;
    copy.detail.file_name = `COA_dummy_${String(n).padStart(3, '0')}.pdf`;
    copy.detail.lot_no = `DUMMY-${String(n).padStart(3, '0')}`;
    copy.detail.uploaded_at = new Date(oldest - n * 3_600_000).toISOString();
    if (copy.extraction) copy.extraction.document_id = id;
    state.docs.push(copy);
  }
}

/**
 * 주소의 ?mock=empty 는 문서가 하나도 없는 상태(시안 2-0), ?mock=anomaly 는 A0266047에 이상 패턴이 있는 상태(시안 2-10),
 * ?mock=issues 는 A0390221에 문서 수준 문제(로트 불일치, 날짜 충돌)가 있어 로트 권고가 보류인 상태([v1.4])로,
 * ?mock=failed-transient 는 실패 문서가 일시 오류(처리 시간 초과, 서버 재시작으로 중단), ?mock=failed-permanent 는 영구 오류(추출·판정 실패),
 * ?mock=multilot 는 A0266047이 한 문서에서 로트 2개가 읽힌 복수 로트인 상태로,
 * ?mock=reissue-conflict 는 A0266047의 같은 로트 CoA가 3개 버전이라 기준 버전을 골라야 하는 상태, ?mock=reissue-review 는 처분된 A0355190에 재발행본이 들어온 상태로,
 * ?mock=sets 는 탄산리튬에 규격 세트가 D1, D3, STRICT, RELAXED인 상태로, ?mock=many 는 문서가 105건인 상태(검수 목록 페이지 넘김 확인)로
 * 목업 데이터를 바꿉니다. 지정하지 않으면 기본 목업(보류 1건, 오류 1건 포함)을 그대로 씁니다.
 */
export function applyMockScenario(): void {
  const flag = devParam('mock');
  const scenarios = ['anomaly', 'issues', 'sets', 'failed-transient', 'failed-permanent', 'multilot', 'reissue-conflict', 'reissue-review'] as const;
  const scenario = scenarios.find((name) => name === flag);
  if (!mockApi || (flag !== 'empty' && flag !== 'many' && !scenario)) return;
  if (flag === 'many') {
    const state = createMockState();
    addManyDocs(state);
    mockApi.resetState(state);
    return;
  }
  mockApi.resetState(createMockState({ empty: flag === 'empty', scenario }));
}
