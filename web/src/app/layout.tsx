import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "UAP 485-x NYC Development Expert",
  description: "NYC zoning, UAP, and 485-x development strategy assistant with live property context and document-grounded recommendations.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" style={{ height: "100%", overflow: "hidden" }}>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`} style={{ height: "100%", overflow: "hidden" }}>
        {children}
      </body>
    </html>
  );
}
