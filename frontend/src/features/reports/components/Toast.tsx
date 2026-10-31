import { useEffect } from 'react'

export interface ToastData {
    type: 'success' | 'error'
    message: string
}

interface Props {
    toast: ToastData | null
    onClose: () => void
}

// 화면 아래에 잠깐 보이는 알림. 5초 뒤 자동으로 닫힘
export default function Toast({ toast, onClose }: Props) {
    useEffect(() => {
        if (!toast) return
        const timer = setTimeout(onClose, 5000)
        return () => clearTimeout(timer)
    }, [toast, onClose])

    if (!toast) return null

    return (
        <div
            role="status"
            className="fixed bottom-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-[#1f2328] px-5 py-3.5 text-sm text-white shadow-lg"
        >
            <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${toast.type === 'success' ? 'border-[#3ddc84] text-[#3ddc84]' : 'border-[#ff7875] text-[#ff7875]'
                    }`}
            >
                {toast.type === 'success' ? '✓' : '!'}
            </span>
            <span>{toast.message}</span>
            <span className="h-4 w-px bg-white/30" />
            <button type="button" onClick={onClose} className="font-bold text-[#8ab4ff]">
                닫기
            </button>
        </div>
    )
}