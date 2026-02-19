import * as pdfjsLib from 'pdfjs-dist';

// Set worker path - use the bundled worker for Vite
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

export async function extractTextFromPDF(file: File): Promise<string> {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    
    let fullText = '';
    
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const textContent = await page.getTextContent();
      
      const pageText = textContent.items
        .map((item: any) => item.str)
        .join(' ');
      
      fullText += `\n\n=== Page ${pageNum} ===\n\n${pageText}`;
    }
    
    return fullText;
  } catch (error) {
    console.error('Error extracting text from PDF:', error);
    throw new Error('Failed to extract text from PDF');
  }
}

// Extract text with position data for bounding box calculation
export async function extractTextWithPositions(file: File): Promise<{
  text: string;
  positions: Array<{ page: number; text: string; x: number; y: number; width: number; height: number }>;
}> {
  try {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    
    let fullText = '';
    const positions: Array<{ page: number; text: string; x: number; y: number; width: number; height: number }> = [];
    
    for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
      const page = await pdf.getPage(pageNum);
      const textContent = await page.getTextContent();
      const viewport = page.getViewport({ scale: 1.0 });
      
      let pageText = '';
      
      textContent.items.forEach((item: any) => {
        const text = item.str;
        if (!text || !text.trim()) return;
        
        pageText += text + ' ';
        
        // Extract position data - transform[4] is x, transform[5] is y
        const x = item.transform[4];
        const y = viewport.height - item.transform[5]; // Convert to top-left origin
        const width = item.width || 0;
        const height = item.height || 12; // Default height if not available
        
        positions.push({
          page: pageNum,
          text: text,
          x: x,
          y: y,
          width: width,
          height: height
        });
      });
      
      fullText += `\n\n=== Page ${pageNum} ===\n\n${pageText}`;
    }
    
    return {
      text: fullText,
      positions: positions
    };
  } catch (error) {
    console.error('Error extracting text with positions from PDF:', error);
    throw new Error('Failed to extract text with positions from PDF');
  }
}

export async function extractFirstPageTitle(file: File): Promise<string> {
  try {
    console.log('Extracting title from:', file.name);
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    
    if (pdf.numPages === 0) {
      console.log('PDF has no pages');
      return '';
    }
    
    const page = await pdf.getPage(1);
    const textContent = await page.getTextContent();
    
    // Extract text items with their positions
    const textItems = textContent.items as any[];
    console.log('Total text items found:', textItems.length);
    
    if (textItems.length === 0) return '';
    
    // Sort items by font size (height) to find the largest text
    const itemsWithSize = textItems
      .filter((item) => item.height && item.str && item.str.trim())
      .map((item) => ({
        text: item.str.trim(),
        height: item.height,
        y: item.transform ? item.transform[5] : 0
      }))
      .sort((a, b) => b.height - a.height);
    
    console.log('Items with size:', itemsWithSize.length);
    
    if (itemsWithSize.length === 0) {
      // Fallback: just get first lines of text
      const fallback = textItems
        .slice(0, 10)
        .map((item) => item.str)
        .join(' ')
        .trim()
        .substring(0, 150);
      console.log('Using fallback title:', fallback);
      return fallback;
    }
    
    // Get the largest font size
    const maxFontSize = itemsWithSize[0].height;
    console.log('Max font size found:', maxFontSize);
    
    // Get all items with large font (within 90% of max size)
    const largeTextItems = itemsWithSize.filter(
      (item) => item.height >= maxFontSize * 0.85
    );
    
    console.log('Large text items found:', largeTextItems.length);
    
    // Join the large text to form title
    const title = largeTextItems
      .map((item) => item.text)
      .join(' ')
      .trim();
    
    console.log('Extracted title:', title);
    
    // If title is too short or empty, try getting more context
    if (title.length < 5) {
      const fallback = itemsWithSize
        .slice(0, 5)
        .map((item) => item.text)
        .join(' ')
        .trim()
        .substring(0, 150);
      console.log('Title too short, using fallback:', fallback);
      return fallback;
    }
    
    return title.substring(0, 150); // Limit to 150 chars
  } catch (error) {
    console.error('Error extracting title from PDF:', error);
    return '';
  }
}