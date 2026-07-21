import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Theme } from "@radix-ui/themes";
import "@radix-ui/themes/styles.css";
import "@fontsource-variable/manrope";
import "./i18n";
import "./styles.css";
import { App } from "./App";
import { ThemeProvider, useTheme } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15_000, retry: 1 }
  }
});

function Root() {
  const { resolvedTheme } = useTheme();
  return (
    <Theme appearance={resolvedTheme} accentColor="blue" grayColor="slate" radius="large" scaling="100%">
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </Theme>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <Root />
    </ThemeProvider>
  </React.StrictMode>
);
