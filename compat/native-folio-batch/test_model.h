/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef NATIVE_FOLIO_BATCH_MODEL_H
#define NATIVE_FOLIO_BATCH_MODEL_H
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define panic(...) do { fprintf(stderr,__VA_ARGS__);fputc('\n',stderr);abort(); } while(0)
#define ASSERT_SLEEPABLE() ((void)0)
struct page { unsigned int refs,wires,puts,validates;bool active; };
struct linux_folio { struct page *netbsd_page; };
static struct page *folio_page(struct linux_folio *folio,size_t index)
{ assert(folio!=NULL&&index==0);return folio->netbsd_page; }
static void linux_page_validate_wired(struct page *page)
{ if(page==NULL||page->refs==0||page->wires==0)panic("batch model: missing live native wire");page->validates++; }
static void folio_put(struct linux_folio *folio)
{ struct page *page=folio->netbsd_page;assert(page&&page->refs&&page->wires);page->puts++;
  if(--page->refs==0){page->wires--;page->active=page->wires==0;} }
#endif
