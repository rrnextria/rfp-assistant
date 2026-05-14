import type { Metadata } from "next";
import "./globals.css";
import { BrandThemeProvider } from "@/components/branding/BrandThemeProvider";

export const metadata: Metadata = {
  title: "RFP Assistant",
  description: "Model-agnostic RFP assistant with citation-backed answers",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background font-sans antialiased">
        <BrandThemeProvider>{children}</BrandThemeProvider>
      </body>
    </html>
  );
}
