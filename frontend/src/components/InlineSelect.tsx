import { CaretDown, Check } from "@phosphor-icons/react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

export interface InlineSelectOption<T extends string> {
  value: T;
  label: ReactNode;
  description?: ReactNode;
}

interface InlineSelectProps<T extends string> {
  value: T;
  options: InlineSelectOption<T>[];
  onChange: (value: T) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  ariaLabel: string;
  disabled?: boolean;
}

export function InlineSelect<T extends string>({
  value,
  options,
  onChange,
  open,
  onOpenChange,
  ariaLabel,
  disabled = false
}: InlineSelectProps<T>) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [openUp, setOpenUp] = useState(false);
  const isOpen = open ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!isOpen) return;
    const closeWhenOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeWhenOutside);
    return () => document.removeEventListener("pointerdown", closeWhenOutside);
  }, [isOpen, setOpen]);

  useLayoutEffect(() => {
    if (!isOpen || !rootRef.current) return;
    const root = rootRef.current;
    const menu = root.querySelector<HTMLElement>(".inline-select-options");
    if (!menu) return;
    const trigger = root.getBoundingClientRect();
    let topLimit = 0;
    let bottomLimit = window.innerHeight;
    for (let parent = root.parentElement; parent; parent = parent.parentElement) {
      if (!/(auto|scroll|hidden)/.test(getComputedStyle(parent).overflowY)) continue;
      const bounds = parent.getBoundingClientRect();
      topLimit = Math.max(topLimit, bounds.top);
      bottomLimit = Math.min(bottomLimit, bounds.bottom);
    }
    const below = bottomLimit - trigger.bottom;
    const above = trigger.top - topLimit;
    setOpenUp(below < menu.getBoundingClientRect().height + 8 && above > below);
  }, [isOpen, options.length]);

  return (
    <div ref={rootRef} className={`inline-select${isOpen ? " inline-select-open" : ""}${isOpen && openUp ? " inline-select-open-up" : ""}${disabled ? " inline-select-disabled" : ""}`}>
      <button
        className="inline-select-trigger"
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        disabled={disabled}
        onClick={() => setOpen(!isOpen)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
          if (event.key === "ArrowDown" && !isOpen) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{selected?.label}</span>
        <CaretDown size={16} weight="bold" aria-hidden="true" />
      </button>
      {isOpen && (
        <div className="inline-select-options" id={listboxId} role="listbox" aria-label={ariaLabel}>
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <button
                className={`inline-select-option${isSelected ? " inline-select-option-selected" : ""}`}
                type="button"
                role="option"
                aria-selected={isSelected}
                key={option.value}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                <span className="inline-select-option-copy">
                  <strong>{option.label}</strong>
                  {option.description && <small>{option.description}</small>}
                </span>
                {isSelected && <Check size={17} weight="bold" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
