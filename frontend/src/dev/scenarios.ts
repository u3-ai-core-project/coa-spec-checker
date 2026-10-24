// [개발 확인용 임시 코드] 시안 비교용 목업 시작 상태. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.
import { mockApi } from '../features/review/shared/api';
import { createMockState } from '../features/review/shared/api/mock/fixtures';
import { devParam } from './params';

/**
 * 주소의 ?mock=empty 는 문서가 하나도 없는 상태(시안 2-0), ?mock=anomaly 는 A0266047에 이상 패턴이 있는 상태(시안 2-10),
 * ?mock=issues 는 A0390221에 문서 수준 문제(로트 불일치, 날짜 충돌)가 있어 로트 권고가 보류인 상태([v1.4])로,
 * ?mock=sets 는 탄산리튬에 규격 세트가 둘(D1, D3)인 상태로 목업 데이터를 바꿉니다. 지정하지 않으면 기본 목업(보류 1건, 오류 1건 포함)을 그대로 씁니다.
 */
export function applyMockScenario(): void {
  const flag = devParam('mock');
  if (!mockApi || (flag !== 'empty' && flag !== 'anomaly' && flag !== 'issues' && flag !== 'sets')) return;
  mockApi.resetState(createMockState({ empty: flag === 'empty', scenario: flag === 'anomaly' || flag === 'issues' || flag === 'sets' ? flag : undefined }));
}
