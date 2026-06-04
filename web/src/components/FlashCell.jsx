import { useEffect, useRef, useState } from "react";

// 变值闪烁:数值变化时背景短暂涨绿/跌红,250ms 衰减;只改 background-color,不改布局。
export default function FlashCell({ value, className = "", children }) {
  const [flash, setFlash] = useState(null);
  const prev = useRef(value);
  useEffect(() => {
    if (value !== prev.current && prev.current !== undefined && value !== undefined && value !== null) {
      setFlash(Number(value) >= Number(prev.current) ? "up" : "down");
      const t = setTimeout(() => setFlash(null), 250);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return <span className={`flash ${flash ? `f-${flash}` : ""} ${className}`}>{children}</span>;
}
