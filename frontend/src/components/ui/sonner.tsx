import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import type { CSSProperties } from "react";

// Theme is driven by our own class-based switcher (<html class="dark">), not
// next-themes, so we resolve it from the DOM and keep it in sync manually.
const Toaster = ({ ...props }: ToasterProps) => {
  const theme: ToasterProps["theme"] = document.documentElement.classList.contains(
    "dark",
  )
    ? "dark"
    : "light";

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--rag-surface)",
          "--normal-text": "var(--rag-primary)",
          "--normal-border": "var(--rag-border)",
          "--border-radius": "var(--radius-lg)",
        } as CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
