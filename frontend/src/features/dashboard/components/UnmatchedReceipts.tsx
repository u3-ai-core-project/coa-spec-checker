import type { UnmatchedReceipt } from '../../upload/batchTypes'

export default function UnmatchedReceipts({ receipts }: { receipts: UnmatchedReceipt[] }) {
    return (
        <section className="overflow-hidden rounded-xl border border-line bg-white">
            <div className="flex items-center justify-between px-5 py-4">
                <h2 className="text-[15px] font-bold text-ink">CoA 미접수 입고 건</h2>
                <span className="text-xs text-ink-sub">{receipts.length}건</span>
            </div>
            {receipts.length === 0 ? (
                <p className="border-t border-line px-5 py-5 text-xs text-[#9aa0a8]">모든 입고 건에 CoA가 연결되었습니다.</p>
            ) : (
                receipts.map((r) => (
                    <div key={r.receipt_id} className="flex flex-col gap-1.5 border-t border-line px-5 py-4">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-ink">{r.received_lot_no}</span>
                            <span className="text-xs text-ink-sub">{r.supplier ?? '-'}</span>
                        </div>
                        <dl className="grid grid-cols-[64px_1fr] gap-y-1 text-xs">
                            <dt className="font-medium text-ink">입고 번호</dt>
                            <dd className="text-ink-sub">{r.receipt_id}</dd>
                            <dt className="font-medium text-ink">입고일</dt>
                            <dd className="text-ink-sub">{r.received_date ?? '-'}</dd>
                        </dl>
                    </div>
                ))
            )}
        </section>
    )
}