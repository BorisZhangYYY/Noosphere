import { CaretDown, Check } from "@phosphor-icons/react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

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

  return (
    <div ref={rootRef} className={`inline-select${isOpen ? " inline-select-open" : ""}${disabled ? " inline-select-disabled" : ""}`}>
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
