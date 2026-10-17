import { useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import type { Bbox } from '../shared/api/types';

// react-pdf(PDF.js) 작업자 스크립트
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();

export interface PdfHighlight {
  key: string;
  bbox: Bbox;
  /** 칠하는 색. 없으면 칠하지 않고 선택 테두리만 그립니다. */
  fill?: string;
  selected: boolean;
}

interface PdfViewerProps {
  fileUrl: string;
  /** 원본이 PDF가 아닌 이미지(PNG, JPG)인지 */
  isImage: boolean;
  page: number;
  highlights: PdfHighlight[];
  onNumPages(count: number): void;
}

/** 원본 PDF(또는 이미지)와 그 위의 근거 하이라이트. 좌표는 페이지 대비 0~1 비율입니다(BBOX_UNIT). */
export default function PdfViewer({ fileUrl, isImage, page, highlights, onNumPages }: PdfViewerProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);

  useEffect(() => {
    const element = boxRef.current;
    if (!element) return;
    const update = () => setWidth(Math.max(280, element.clientWidth));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // 선택한 항목의 하이라이트가 보이도록 스크롤합니다.
  const selected = highlights.find((highlight) => highlight.selected && highlight.bbox.page === page);
  const selectedRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [selected?.key, page]);

  const visible = highlights.filter((highlight) => highlight.bbox.page === page && (highlight.fill || highlight.selected));

  const overlay = (
    <div className="pdf-highlights pointer-events-none absolute inset-0">
      {visible.map((highlight) => (
        <div
          key={highlight.key}
          ref={highlight.selected ? selectedRef : undefined}
          className={`pdf-highlight absolute rounded${
            highlight.selected ? ' outline outline-2 outline-offset-2 outline-[#2B4FCB]' : ''
          }`}
          style={{
            left: `${highlight.bbox.x * 100}%`,
            top: `${highlight.bbox.y * 100}%`,
            width: `${highlight.bbox.w * 100}%`,
            height: `${highlight.bbox.h * 100}%`,
            backgroundColor: highlight.fill,
            mixBlendMode: 'multiply',
          }}
        />
      ))}
    </div>
  );

  return (
    <div ref={boxRef} className="h-full w-full overflow-auto">
      <div className="pdf-page relative" style={{ width }}>
        {isImage ? (
          <img src={fileUrl} alt="원본 문서" className="block w-full" onLoad={() => onNumPages(1)} />
        ) : (
          <Document
            file={fileUrl}
            onLoadSuccess={({ numPages }) => onNumPages(numPages)}
            loading={<div className="p-6 text-[13px] text-[#8A9099]">원본을 불러오는 중입니다.</div>}
            error={<div className="p-6 text-[13px] text-[#C0342E]">원본을 표시하지 못했습니다.</div>}
          >
            <Page pageNumber={page} width={width} renderTextLayer={false} renderAnnotationLayer={false} />
          </Document>
        )}
        {overlay}
      </div>
    </div>
  );
}
