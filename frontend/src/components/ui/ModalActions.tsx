export function ModalActions({ onClose, submitLabel }: { onClose: () => void; submitLabel: string }) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <button className="secondary-button" onClick={onClose} type="button">
        Cancel
      </button>
      <button className="primary-button" type="submit">
        {submitLabel}
      </button>
    </div>
  );
}
