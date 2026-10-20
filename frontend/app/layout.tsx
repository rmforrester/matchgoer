import type { Metadata } from "next";
import { Barlow_Condensed, Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import Navigation from "./components/Navigation";
import AuthProvider from "./components/AuthProvider";
import AnalyticsConsent from "./components/AnalyticsConsent";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const barlowCondensed = Barlow_Condensed({
  variable: "--font-barlow-condensed",
  subsets: ["latin"],
  weight: ["600", "700", "800", "900"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Matchgoer",
  description: "Find football worth going to. Discover matches wherever you are and know the matchday before you get there.",
  icons: { icon: "/favicon.ico" },
  openGraph: {
    title: "Matchgoer",
    description: "Find football worth going to. Discover matches wherever you are and know the matchday before you get there.",
    type: "website",
    siteName: "Matchgoer",
    images: [{
      url: "https://beta.matchgoer.com/brand/matchgoer-social-preview.png",
      width: 1200,
      height: 630,
      type: "image/png",
      alt: "Matchgoer circular badge with a football and the words Find Your Football",
    }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Matchgoer",
    description: "Find football worth going to. Discover matches wherever you are and know the matchday before you get there.",
    images: [{
      url: "https://beta.matchgoer.com/brand/matchgoer-social-preview.png",
      alt: "Matchgoer circular badge with a football and the words Find Your Football",
    }],
  },
};

export default function RootLayout({
  children,
}: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${barlowCondensed.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <Suspense fallback={null}>
            <Navigation />
          </Suspense>
          {children}
          <Suspense fallback={null}><AnalyticsConsent /></Suspense>
        </AuthProvider>
      </body>
    </html>
  );
}
