// [개발 확인용 임시 코드] 다른 파트 화면(업로드, 대시보드, 리포트)의 자리입니다. 시연용 미리보기 페이지입니다. 실제 서비스 화면에는 포함되지 않습니다.

/** 다른 파트(업로드, 대시보드, 리포트)가 구현할 화면의 자리입니다. 제목은 공통 레이아웃의 헤더가 보여 줍니다. */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="rounded-xl border border-[#E3E5E8] bg-white p-6 text-[14px] text-[#5B616A]">
      {title} 화면은 다른 파트에서 구현합니다.
    </div>
  );
}
