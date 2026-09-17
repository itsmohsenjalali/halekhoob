export default function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <img
      className="brand-mark"
      src="/brand/mark.svg"
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
    />
  );
}
