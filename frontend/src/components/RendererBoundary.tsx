import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./ui/button";

interface FallbackProps {
  message: string;
  action: string;
  onReload: () => void;
}

interface BoundaryProps extends FallbackProps {
  children: ReactNode;
}

interface BoundaryState {
  failed: boolean;
}

/**
 * Catches a renderer that throws while rendering — above all a code-split
 * chunk (multi/ranking/matrix) whose hashed file no longer exists after a
 * deploy, which React.lazy rethrows during render. Without it React unmounts
 * the whole runner into a blank page; here the question area shows the
 * message and a reload, which fetches the current build (the response id in
 * storage keeps the participant's place).
 */
class Boundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) console.error("renderer failed", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" data-testid="renderer-error">
        <p className="text-error">{this.props.message}</p>
        <Button variant="surface" size="runner-sm" className="mt-4" onClick={this.props.onReload}>
          {this.props.action}
        </Button>
      </div>
    );
  }
}

/** The runner's error boundary around a question's control, with chrome strings from i18next. */
export function RendererBoundary({ children, onReload = () => window.location.reload() }: { children: ReactNode; onReload?: () => void }) {
  const { t } = useTranslation();
  return (
    <Boundary message={t("app.error")} action={t("app.reload")} onReload={onReload}>
      {children}
    </Boundary>
  );
}
