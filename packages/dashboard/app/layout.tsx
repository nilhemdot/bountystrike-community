import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "BountyStrike — Control Plane",
  description:
    "Operator dashboard for the BountyStrike autonomous bug bounty platform. Monitor findings, program EV, agent activity, and approval queues.",
  robots: "noindex, nofollow",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#080b0f",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`bg-background ${inter.variable} ${GeistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
