import { FileText, BarChart3, ArrowRight } from 'lucide-react';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { useUploadStore } from '../../stores/uploadStore';

export function RecentUploads() {
  const files = useUploadStore((s) => s.files);
  const recentFiles = files.filter((f) => f.response).slice(-5).reverse();

  if (recentFiles.length === 0) return null;

  const getFileSize = (size: number) => {
    const sizeInMB = size / (1024 * 1024);
    return sizeInMB > 1 
      ? `${sizeInMB.toFixed(2)} MB` 
      : `${(size / 1024).toFixed(0)} KB`;
  };

  const getTimeAgo = (date: string | Date) => {
    const now = new Date();
    const then = new Date(date);
    const diff = now.getTime() - then.getTime();
    const minutes = Math.floor(diff / 60000);
    
    if (minutes < 1) return 'Just now';
    if (minutes === 1) return '1 minute ago';
    if (minutes < 60) return `${minutes} minutes ago`;
    
    const hours = Math.floor(minutes / 60);
    if (hours === 1) return '1 hour ago';
    return `${hours} hours ago`;
  };

  return (
    <Card className="overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-blue-50 to-purple-50">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-gray-700" />
          <h2 className="text-lg font-semibold text-gray-900">Recent Uploads</h2>
        </div>
        <Button 
          variant="ghost" 
          size="sm"
          className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
        >
          View All
          <ArrowRight className="w-4 h-4 ml-1" />
        </Button>
      </div>

      <div className="p-6 space-y-3">
        {recentFiles.map((file) => (
          <div
            key={file.id}
            className="group p-4 border border-gray-200 rounded-xl hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4 flex-1">
                <div className="w-12 h-12 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0 group-hover:bg-blue-100 transition-colors">
                  <FileText className="w-6 h-6 text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-gray-900 truncate">
                    {file.file.name}
                  </h3>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-sm text-gray-500">
                      {getFileSize(file.file.size)}
                    </span>
                    <span className="text-sm text-gray-400">•</span>
                    <span className="text-sm text-gray-500">
                      {file.response?.uploadedAt ? getTimeAgo(file.response.uploadedAt) : 'Recently'}
                    </span>
                  </div>
                </div>
              </div>

              <Button 
                size="sm"
                variant="ghost"
                className="opacity-0 group-hover:opacity-100 transition-opacity text-blue-600 hover:bg-blue-50"
              >
                View
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}