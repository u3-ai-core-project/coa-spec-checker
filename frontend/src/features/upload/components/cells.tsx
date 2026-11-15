export const GRID = 'grid grid-cols-[minmax(0,1fr)_100px_300px_100px] items-center px-5'

export function Spinner() {
    return <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-brand/25 border-t-brand" />
}

export function Mark({ color, children }: { color: string; children: string }) {
    return (
        <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[11px] font-bold text-white ${color}`}>
            {children}
        </span>
    )
}