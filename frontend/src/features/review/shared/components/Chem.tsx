import type { ReactNode } from 'react';

// 화학식 안의 숫자만 아래 첨자로 바꿉니다. LOT 번호나 등급(D1)처럼 일반 텍스트는 건드리지 않습니다.
// SO42−는 황산 이온(SO₄²⁻)으로, 4는 아래 첨자, 2−는 위 첨자로 씁니다.
const FORMULA = /(Li2CO3|Na2O|K2O|Fe2O3|SO42−|SO3|SO4)/g;

/** 문자열 안의 화학식(Li2CO3, Na2O, SO42− 등)을 첨자로 표시합니다. */
export function Chem({ text }: { text: string }) {
  const parts = text.split(FORMULA);
  const nodes: ReactNode[] = parts.map((part, index) => {
    if (index % 2 === 0) return part;
    if (part === 'SO42−') {
      return (
        <span key={index}>
          SO<sub>4</sub>
          <sup>2−</sup>
        </span>
      );
    }
    return (
      <span key={index}>
        {part.split(/(\d+)/).map((piece, i) => (i % 2 === 1 ? <sub key={i}>{piece}</sub> : piece))}
      </span>
    );
  });
  return <>{nodes}</>;
}
