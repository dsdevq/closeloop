export function TextField({
  label,
  onChange,
  required,
  type = 'text',
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  type?: string;
  value: string;
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <input className="field-input" value={value} onChange={(event) => onChange(event.target.value)} required={required} type={type} />
    </label>
  );
}
