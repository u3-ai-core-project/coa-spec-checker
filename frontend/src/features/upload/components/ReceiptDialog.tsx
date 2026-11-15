import { useState } from 'react'
import { SUPPLIERS } from '../lib/upload'
import type { ReceiptInfo } from '../hooks/useUploadQueue'

interface Props {
    fileName: string
    onCancel: () => void
    onSubmit: (info: ReceiptInfo) => void
}

// 입력값 정리: 앞뒤 공백 제거 후, 대소문자 무시하고 기존 협력사와 같으면 기존 표기를 사용
function normalizeSupplier(input: string): string {
    const trimmed = input.trim()
    const match = SUPPLIERS.find((s) => s.toLowerCase() === trimmed.toLowerCase())
    return match ?? trimmed
}

export default function ReceiptDialog({ fileName, onCancel, onSubmit }: Props) {
    const [lot, setLot] = useState('')
    const [supplier, setSupplier] = useState('')
    const valid = lot.trim() !== '' && supplier.trim() !== ''

    return (
        <div
            className="fixed inset-0 z-20 flex items-center justify-center bg-black/50 p-6"
            role="dialog"
            aria-modal="true"
            aria-labelledby="receipt-title"
        >
            <form
                onSubmit={(e) => {
                    e.preventDefault()
                    if (valid) onSubmit({ receivedLotNo: lot.trim(), supplier: normalizeSupplier(supplier) })
                }}
                className="w-full max-w-[400px] rounded-2xl bg-white p-6"
            >
                <h2 id="receipt-title" className="text-xl font-bold text-ink">
                    입고 정보 입력
                </h2>
                <p className="mt-4 text-sm text-ink-sub">
                    {fileName}와 검수 화면의 발주 정보와 일치 판단 근거로 사용됩니다.
                </p>

                <label htmlFor="received-lot" className="mt-5 block text-sm text-ink">
                    입고 로트번호 <span className="text-[#c0392b]">*</span>
                </label>
                <input
                    id="received-lot"
                    value={lot}
                    onChange={(e) => setLot(e.target.value)}
                    placeholder="예 : A0511877"
                    autoFocus
                    className="mt-2 w-full rounded-lg border border-line px-3 py-2.5 text-sm outline-none focus:border-brand"
                />

                <label htmlFor="supplier" className="mt-4 block text-sm text-ink">
                    협력사 <span className="text-[#c0392b]">*</span>
                </label>
                <input
                    id="supplier"
                    list="supplier-options"
                    value={supplier}
                    onChange={(e) => setSupplier(e.target.value)}
                    placeholder="목록에서 고르거나 직접 입력"
                    autoComplete="off"
                    className="mt-2 w-full rounded-lg border border-line px-3 py-2.5 text-sm outline-none focus:border-brand"
                />
                <datalist id="supplier-options">
                    {SUPPLIERS.map((s) => (
                        <option key={s} value={s} />
                    ))}
                </datalist>

                <div className="mt-5 flex gap-2">
                    <button
                        type="button"
                        onClick={onCancel}
                        className="flex-1 rounded-lg border border-line bg-white py-2.5 text-sm text-ink hover:bg-surface"
                    >
                        취소
                    </button>
                    <button
                        type="submit"
                        disabled={!valid}
                        className="flex-1 rounded-lg bg-brand py-2.5 text-sm font-bold text-white disabled:bg-[#eceef1] disabled:text-[#9aa0a8]"
                    >
                        저장하고 검수 시작
                    </button>
                </div>
            </form>
        </div>
    )
}