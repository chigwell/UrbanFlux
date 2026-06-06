"use client"

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"

// Context
interface ExpandableScreenContextValue {
  isExpanded: boolean
  expand: () => void
  collapse: () => void
  layoutId: string
  triggerRadius: string
  contentRadius: string
}

const ExpandableScreenContext =
  createContext<ExpandableScreenContextValue | null>(null)

function useExpandableScreen() {
  const context = useContext(ExpandableScreenContext)
  if (!context) {
    throw new Error(
      "useExpandableScreen must be used within an ExpandableScreen"
    )
  }
  return context
}

// Root Component
interface ExpandableScreenProps {
  children: ReactNode
  defaultExpanded?: boolean
  onExpandChange?: (expanded: boolean) => void
  layoutId?: string
  triggerRadius?: string
  contentRadius?: string
  animationDuration?: number
  lockScroll?: boolean
}

export function ExpandableScreen({
  children,
  defaultExpanded = false,
  onExpandChange,
  layoutId = "expandable-card",
  triggerRadius = "100px",
  contentRadius = "24px",
  animationDuration = 0.3,
  lockScroll = true,
}: ExpandableScreenProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  const expand = () => {
    setIsExpanded(true)
    onExpandChange?.(true)
  }

  const collapse = () => {
    setIsExpanded(false)
    onExpandChange?.(false)
  }

  useEffect(() => {
    if (lockScroll) {
      if (isExpanded) {
        document.body.style.overflow = "hidden"
      } else {
        document.body.style.overflow = "unset"
      }
    }
  }, [isExpanded, lockScroll])

  useEffect(() => {
    if (!isExpanded) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        collapse()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [isExpanded])

  return (
    <ExpandableScreenContext.Provider
      value={{
        isExpanded,
        expand,
        collapse,
        layoutId,
        triggerRadius,
        contentRadius,
    }}
  >
      {children}
    </ExpandableScreenContext.Provider>
  )
}

// Trigger Component
interface ExpandableScreenTriggerProps {
  children: ReactNode
  className?: string
}

export function ExpandableScreenTrigger({
  children,
  className = "",
}: ExpandableScreenTriggerProps) {
  const { isExpanded, expand, layoutId, triggerRadius } = useExpandableScreen()

  return (
    !isExpanded ? (
      <div className={`relative block w-full min-w-0 ${className}`}>
        <div
          style={{ borderRadius: triggerRadius }}
          className="absolute inset-0 overflow-hidden transform-gpu will-change-transform"
          data-layout-id={layoutId}
        />
        <div
          onClick={expand}
          className="relative min-w-0 cursor-pointer overflow-hidden"
        >
          {children}
        </div>
      </div>
    ) : null
  )
}

// Content Component
interface ExpandableScreenContentProps {
  children: ReactNode
  className?: string
  showCloseButton?: boolean
  closeButtonClassName?: string
}

export function ExpandableScreenContent({
  children,
  className = "",
  showCloseButton = true,
  closeButtonClassName = "",
}: ExpandableScreenContentProps) {
  const { isExpanded, collapse, layoutId, contentRadius } = useExpandableScreen()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return null
  }

  return createPortal(
    isExpanded ? (
      <div
        key="expandable-screen"
        className="fixed inset-0 z-200 flex items-center justify-center p-3 sm:p-2"
      >
        <div
          data-layout-id={layoutId}
          style={{ borderRadius: contentRadius }}
          className={`relative flex h-full w-full overflow-hidden transform-gpu will-change-transform ${className}`}
        >
          <div className="relative z-20 h-full w-full min-w-0 overflow-x-hidden overflow-y-auto">
            {children}
          </div>
        </div>

        {showCloseButton && (
          <button
            onClick={collapse}
            className={`absolute right-8 top-8 z-30 flex h-10 w-10 items-center justify-center rounded-full transition-colors sm:right-6 sm:top-6 ${
              closeButtonClassName ||
              "text-primary-foreground bg-transparent hover:bg-primary-foreground/10"
            }`}
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>
    ) : null,
    document.body,
  )
}

// Background Component (optional)
interface ExpandableScreenBackgroundProps {
  trigger?: ReactNode
  content?: ReactNode
  className?: string
}

export function ExpandableScreenBackground({
  trigger,
  content,
  className = "",
}: ExpandableScreenBackgroundProps) {
  const { isExpanded } = useExpandableScreen()

  if (isExpanded && content) {
    return <div className={className}>{content}</div>
  }

  if (!isExpanded && trigger) {
    return <div className={className}>{trigger}</div>
  }

  return null
}

export { useExpandableScreen }
