import { useEffect, useRef, useState } from 'react'
import { MATERIALS } from '../lib/upload'
import { ChevronDownIcon } from '../../../components/icons'

interface Props {
    value: string
    onChange: (code: string) => void
}

export default function MaterialSelect({ value, onChange }: Props) {
    const [open, setOpen] = useState(false)
    const boxRef = useRef<HTMLDivElement>(null)
    const current = MATERIALS.find((m) => m.code === value) ?? MATERIALS[0]

    useEffect(() => {
        function close(e: MouseEvent) {
            if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
        }
        document.addEventListener('mousedown', close)
        return () => document.removeEventListener('mousedown', close)
    }, [])

    return (
        <div className="flex items-center gap-3.5">
            <span className="text-sm font-bold text-ink">원자재</span>
            <div ref={boxRef} className="relative w-[220px]">
                <button
                    type="button"
                    onClick={() => setOpen(!open)}
                    aria-expanded={open}
                    className="flex h-[41px] w-full items-center gap-2 rounded-lg border border-[#cfd4da] bg-white px-3.5 text-left"
                >
                    <span className="text-sm font-bold text-ink">{current.name}</span>
                    <span className="text-[13px] text-[#808080]">{current.formula}</span>
                    <ChevronDownIcon className="ml-auto" />
                </button>
                {open && (
                    <ul className="absolute left-0 top-full z-10 mt-1 w-full overflow-hidden rounded-lg border border-line bg-white shadow-sm">
                        {MATERIALS.map((m) => (
                            <li key={m.code}>
                                <button
                                    type="button"
                                    disabled={!m.enabled}
                                    onClick={() => {
                                        onChange(m.code)
                                        setOpen(false)
                                    }}
                                    className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm text-ink hover:bg-surface disabled:cursor-not-allowed disabled:text-[#9aa0a8] disabled:hover:bg-white"
                                >
                                    <span className={m.code === value ? 'font-bold text-brand' : ''}>{m.name}</span>
                                    <span className="text-[13px] text-[#808080]">{m.formula}</span>
                                    {!m.enabled && <span className="ml-auto text-xs">준비 중</span>}
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    )
}