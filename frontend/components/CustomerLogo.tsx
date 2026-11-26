"use client";
import { API_URL } from '@/app/services/api';
import { useBranding, type Branding } from '@/lib/branding';
import { cn } from '@/lib/utils';
import React from 'react';

interface CustomerLogoProps {
  /** Fläche, auf der das Logo steht: wählt die passende Logo-Variante. */
  surface: 'light' | 'dark';
  className?: string;
  /** Feste Box, in die das Logo nur eingepasst wird (Tailwind-Klassen). */
  boxClassName?: string;
  /** Vorschau im Corporate-Tab: ungespeicherten Stand statt des aktiven Brandings zeigen. */
  branding?: Branding;
}

/**
 * Kundenlogo an einem festen Platz. Fehlt die passende Variante, wird die andere einfarbig
 * gezeigt (weiß auf dunkel, schwarz auf hell); ohne Logo erscheint der Kundenname als Text.
 */
export function CustomerLogo({ surface, className, boxClassName = 'h-7 max-w-[160px]', branding }: CustomerLogoProps) {
  const active = useBranding();
  const b = branding ?? active;
  const preferred = surface === 'dark' ? b.logo_dark_url : b.logo_light_url;
  const fallback = surface === 'dark' ? b.logo_light_url : b.logo_dark_url;
  const src = preferred ?? fallback;

  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- Logo kommt zur Laufzeit vom Backend, nicht aus dem Build
      <img
        src={src.startsWith('/') ? `${API_URL}${src}` : src}
        alt={b.customer_name ?? ''}
        className={cn(
          'block w-auto object-contain object-left',
          boxClassName,
          !preferred && (surface === 'dark' ? 'brightness-0 invert' : 'brightness-0'),
          className,
        )}
      />
    );
  }
  if (b.customer_name) {
    return (
      <span className={cn('codena-kicker truncate', surface === 'dark' ? 'text-ds-zinc-300' : 'text-ds-zinc-600', className)}>
        {b.customer_name}
      </span>
    );
  }
  return null;
}

export function hasCustomerIdentity(b: Branding): boolean {
  return Boolean(b.logo_light_url || b.logo_dark_url || b.customer_name);
}
